import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

"""
Glue Job: normalize_provider_vectors

Input:
  --in_s3   s3://.../communities/runs/<run_id>/vectors/vectors_sparse/
  --out_s3  s3://.../communities/runs/<run_id>/vectors/
  --year    2023

Output:
  out_s3/vectors_l2/  (Parquet, partitioned by year)
  out_s3/norm_stats/year=YYYY/  (Parquet)

Behavior:
- Computes L2 norm from sparse values: sqrt(sum(v^2))
- Divides values by norm
- Drops rows with norm <= eps

Optional:
  --eps  (default 1e-12)
"""

args = getResolvedOptions(sys.argv, ["in_s3", "out_s3", "year"] + (["eps"] if "--eps" in sys.argv else []))

spark = SparkSession.builder.getOrCreate()
spark.conf.set("spark.sql.shuffle.partitions", "600")

IN_S3 = args["in_s3"].rstrip("/") + "/"
OUT_S3 = args["out_s3"].rstrip("/") + "/"
YEAR = int(args["year"])
EPS = float(args.get("eps", "1e-12"))

# -----------------------
# Read vectors
# -----------------------
df = spark.read.parquet(IN_S3).filter(F.col("year") == YEAR)

# Expected columns:
# row_id, npi, year, dim, indices (array<int>), values (array<float>)
required = {"row_id", "npi", "year", "dim", "indices", "values"}
missing = required - set(df.columns)
if missing:
    raise ValueError(f"Missing required columns: {sorted(missing)}")

# -----------------------
# Compute L2 norm from sparse values
# -----------------------
# norm2 = sum(v_i^2)
df = df.withColumn(
    "norm2",
    F.expr("aggregate(values, cast(0.0 as double), (acc, x) -> acc + double(x)*double(x))")
)

df = df.withColumn("norm", F.sqrt(F.col("norm2")))

# Track stats before filtering
total = df.count()
zeroish = df.filter(F.col("norm") <= F.lit(EPS)).count()

# Drop near-zero vectors
df2 = df.filter(F.col("norm") > F.lit(EPS))

# -----------------------
# Normalize values
# -----------------------
# values_norm = values / norm
df2 = df2.withColumn(
    "values",
    F.expr("transform(values, x -> float(double(x) / double(norm)))")
)

# Clean up
out = df2.drop("norm2", "norm")

# -----------------------
# Write normalized vectors
# -----------------------
(out
 .write
 .mode("overwrite")
 .partitionBy("year")
 .parquet(OUT_S3 + "vectors_l2/"))

# -----------------------
# Write stats (tiny)
# -----------------------
stats = spark.createDataFrame(
    [(YEAR, total, zeroish, total - zeroish, EPS)],
    ["year", "total_vectors", "dropped_zero_norm", "kept_vectors", "eps"]
)

(stats
 .write
 .mode("overwrite")
 .parquet(OUT_S3 + f"norm_stats/year={YEAR}/"))

print(f"✅ Normalized vectors. year={YEAR} total={total} dropped={zeroish} kept={total-zeroish}")
