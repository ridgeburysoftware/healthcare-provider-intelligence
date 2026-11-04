import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

"""
Glue Job: build_provider_vectors

Inputs (Parquet in S3):
  --hcpcs_s3    s3://.../features/provider_hcpcs/
  --drugs_s3    s3://.../features/provider_drugs/
  --unified_s3  s3://.../features/provider_unified/        (optional)
  --out_s3      s3://.../communities/runs/<run_id>/vectors/
  --year        2023

Optional:
  --include_scalars  0|1 (default 1)
  --scalar_cols      comma-separated list (default: allowed_per_service,cost_per_claim)
  --min_value        drop tiny values (default 1e-8)
  --max_dim          cap vocab size (default 200000)  # safety valve
"""

req = ["hcpcs_s3", "drugs_s3", "out_s3", "year"]
opt = []
if "--unified_s3" in sys.argv:
    opt.append("unified_s3")
if "--include_scalars" in sys.argv:
    opt.append("include_scalars")
if "--scalar_cols" in sys.argv:
    opt.append("scalar_cols")
if "--min_value" in sys.argv:
    opt.append("min_value")
if "--max_dim" in sys.argv:
    opt.append("max_dim")

args = getResolvedOptions(sys.argv, req + opt)

spark = SparkSession.builder.getOrCreate()
spark.conf.set("spark.sql.shuffle.partitions", "600")

YEAR = int(args["year"])
HCPCS_S3 = args["hcpcs_s3"].rstrip("/") + "/"
DRUGS_S3 = args["drugs_s3"].rstrip("/") + "/"
OUT_S3 = args["out_s3"].rstrip("/") + "/"

INCLUDE_SCALARS = int(args.get("include_scalars", "1"))
SCALAR_COLS = (args.get("scalar_cols", "allowed_per_service,cost_per_claim") or "").split(",")
SCALAR_COLS = [c.strip() for c in SCALAR_COLS if c.strip()]
MIN_VALUE = float(args.get("min_value", "1e-8"))
MAX_DIM = int(args.get("max_dim", "200000"))

def read_parquet(path: str):
    return spark.read.parquet(path)

# -----------------------
# Load long-form features
# -----------------------
h = read_parquet(HCPCS_S3).filter(F.col("year") == YEAR).select("npi", "year", "feature_id", "value")
d = read_parquet(DRUGS_S3).filter(F.col("year") == YEAR).select("npi", "year", "feature_id", "value")

features = h.unionByName(d)

# Clean / normalize
features = (
    features
    .withColumn("npi", F.col("npi").cast("string"))
    .withColumn("feature_id", F.col("feature_id").cast("string"))
    .withColumn("value", F.col("value").cast("double"))
    .filter(F.col("npi").isNotNull() & (F.length("npi") == 10))
    .filter(F.col("feature_id").isNotNull() & (F.length("feature_id") > 0))
    .filter(F.col("value").isNotNull())
    .filter(F.abs(F.col("value")) >= F.lit(MIN_VALUE))
)

# Optional: add scalar features from unified
if INCLUDE_SCALARS and ("unified_s3" in args) and SCALAR_COLS:
    U_S3 = args["unified_s3"].rstrip("/") + "/"
    u = read_parquet(U_S3).filter(F.col("year") == YEAR).select(["npi", "year"] + SCALAR_COLS)

    # Turn each scalar column into feature rows like S:allowed_per_service, S:cost_per_claim
    scalar_rows = None
    for c in SCALAR_COLS:
        tmp = (
            u.select(
                F.col("npi").cast("string").alias("npi"),
                F.col("year").alias("year"),
                F.lit(f"S:{c}").alias("feature_id"),
                F.col(c).cast("double").alias("value"),
            )
            .filter(F.col("value").isNotNull())
        )
        scalar_rows = tmp if scalar_rows is None else scalar_rows.unionByName(tmp)

    if scalar_rows is not None:
        features = features.unionByName(scalar_rows)

# -----------------------
# Build vocabulary (feature_id -> idx)
# -----------------------
# Vocab by global frequency (how many NPIs have it). Helps stability.
feat_freq = features.groupBy("feature_id").agg(F.countDistinct("npi").alias("df"))

# Cap vocabulary size as safety valve
vocab = (
    feat_freq.orderBy(F.desc("df"), F.asc("feature_id"))
    .limit(MAX_DIM)
    .withColumn("idx", F.row_number().over(Window.orderBy(F.desc("df"), F.asc("feature_id"))) - 1)
    .select("feature_id", "idx", "df")
)

dim = vocab.count()  # small-ish action; ok once per run

# Persist vocab
(vocab
 .write.mode("overwrite")
 .parquet(OUT_S3 + f"vocab/year={YEAR}/"))

# -----------------------
# Map features -> sparse vector rows per npi
# -----------------------
f2 = (
    features.join(vocab.select("feature_id", "idx"), on="feature_id", how="inner")
    .select("npi", "year", "idx", F.col("value").cast("float").alias("value"))
)

# Aggregate into sparse vector representation: sorted (idx, value) arrays
# (Spark has no stable order in collect_list, so we collect structs and sort_array)
vec = (
    f2.groupBy("npi", "year")
    .agg(F.sort_array(F.collect_list(F.struct("idx", "value"))).alias("pairs"))
    .withColumn("indices", F.expr("transform(pairs, x -> x.idx)"))
    .withColumn("values", F.expr("transform(pairs, x -> x.value)"))
    .drop("pairs")
    .withColumn("dim", F.lit(int(dim)))
)

# Assign a stable row_id to each npi for later FAISS ordering / graph
provider_index = (
    vec.select("npi").distinct()
    .withColumn("row_id", F.row_number().over(Window.orderBy("npi")) - 1)
)

# Join row_id onto vectors
vec2 = vec.join(provider_index, on="npi", how="inner").select("row_id", "npi", "year", "dim", "indices", "values")

# Write outputs
(vec2
 .write.mode("overwrite")
 .partitionBy("year")
 .parquet(OUT_S3 + "vectors_sparse/"))

(provider_index
 .write.mode("overwrite")
 .parquet(OUT_S3 + f"provider_index/year={YEAR}/"))

print(f"✅ Wrote sparse vectors. year={YEAR} dim={dim} providers={provider_index.count()}")
