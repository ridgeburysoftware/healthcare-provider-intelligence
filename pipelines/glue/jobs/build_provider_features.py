import sys
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

"""
Glue Job: build_provider_features

Inputs (CSV in S3):
  --partb_s3      s3://bucket/cms/raw/partb/2023/
  --partd_s3      s3://bucket/cms/raw/partd/2023/
  --nppes_s3      s3://bucket/cms/raw/nppes/2026-01-11/
  --out_s3        s3://bucket/communities/runs/<run_id>/features/
  --year          2023
  --topk_hcpcs    500
  --topk_drugs    500
  --drug_key      generic|brand   (optional; default=generic)
"""

args = getResolvedOptions(
    sys.argv,
    [
        "partb_s3",
        "partd_s3",
        "nppes_s3",
        "out_s3",
        "year",
        "topk_hcpcs",
        "topk_drugs",
    ] + (["drug_key"] if "--drug_key" in sys.argv else [])
)

spark = SparkSession.builder.getOrCreate()
spark.conf.set("spark.sql.shuffle.partitions", "400")

YEAR = int(args["year"])
TOPK_HCPCS = int(args["topk_hcpcs"])
TOPK_DRUGS = int(args["topk_drugs"])
DRUG_KEY = (args.get("drug_key", "generic") or "generic").strip().lower()

PARTB_S3 = args["partb_s3"].rstrip("/") + "/"
PARTD_S3 = args["partd_s3"].rstrip("/") + "/"
NPPES_S3 = args["nppes_s3"].rstrip("/") + "/"
OUT_S3 = args["out_s3"].rstrip("/") + "/"

# ---------------------------
# Helpers
# ---------------------------
def read_csv(path: str):
    return (
        spark.read.option("header", True)
        .option("inferSchema", False)
        .option("multiLine", False)
        .option("quote", '"')
        .option("escape", '"')
        .option("mode", "PERMISSIVE")
        .csv(path)
    )

def clean_zip5(col):
    # NPPES postal often includes ZIP+4; keep first 5 digits
    return F.regexp_extract(F.col(col).cast("string"), r"^(\d{5})", 1)

def zip5_to_zip3(zip5_col):
    return F.substring(clean_zip5(zip5_col), 1, 3)

def norm_npi(col):
    return F.regexp_extract(F.col(col).cast("string"), r"(\d{10})", 1)

# ---------------------------
# Column mapping (FINAL)
# ---------------------------
PB_NPI = "Rndrng_NPI"
PB_HCPCS = "HCPCS_Cd"
PB_AVG_ALLOWED = "Avg_Mdcr_Alowd_Amt"
PB_SERVICES = "Tot_Srvcs"
PB_STATE = "Rndrng_Prvdr_State_Abrvtn"
PB_CITY = "Rndrng_Prvdr_City"
PB_ZIP5 = "Rndrng_Prvdr_Zip5"
PB_TAXON = "Rndrng_Prvdr_Type"

PD_NPI = "Prscrbr_NPI"
PD_BRAND = "Brnd_Name"
PD_GENERIC = "Gnrc_Name"
PD_COST = "Tot_Drug_Cst"
PD_CLAIMS = "Tot_Clms"
PD_STATE = "Prscrbr_State_Abrvtn"
PD_CITY = "Prscrbr_City"
PD_TAXON = "Prscrbr_Type"

NP_NPI = "NPI"
NP_CITY = "Provider Business Practice Location Address City Name"
NP_STATE = "Provider Business Practice Location Address State Name"
NP_ZIP = "Provider Business Practice Location Address Postal Code"
NP_TAXON = "Healthcare Provider Taxonomy Code_1"

# ---------------------------
# Load raw
# ---------------------------
pb_raw = read_csv(PARTB_S3).withColumn("year", F.lit(YEAR))
pd_raw = read_csv(PARTD_S3).withColumn("year", F.lit(YEAR))
np_raw = read_csv(NPPES_S3)

# Normalize NPPEs headers (remove quotes) by selecting via exact name as read by Spark.
# Spark will strip the quotes in header parsing; the names appear without quotes.
np = (
    np_raw
    .withColumn("npi", norm_npi(NP_NPI))
    .select(
        "npi",
        F.col(NP_CITY).alias("nppes_city"),
        F.col(NP_STATE).alias("nppes_state"),
        clean_zip5(NP_ZIP).alias("nppes_zip5"),
        F.col(NP_TAXON).alias("nppes_taxonomy_code"),
    )
    .filter(F.col("npi").isNotNull() & (F.length("npi") == 10))
)

# ---------------------------
# PART B: provider_hcpcs (long-form) + pb_unified scalars
# ---------------------------
pb = (
    pb_raw
    .withColumn("npi", norm_npi(PB_NPI))
    .select(
        "npi",
        "year",
        F.col(PB_HCPCS).alias("hcpcs_cd"),
        F.col(PB_AVG_ALLOWED).cast("double").alias("avg_allowed"),
        F.col(PB_SERVICES).cast("double").alias("tot_srvcs"),
        F.col(PB_STATE).alias("pb_state"),
        F.col(PB_CITY).alias("pb_city"),
        clean_zip5(PB_ZIP5).alias("pb_zip5"),
        F.col(PB_TAXON).alias("pb_taxonomy"),
    )
    .filter(F.col("npi").isNotNull() & (F.length("npi") == 10))
    .filter(F.col("hcpcs_cd").isNotNull() & (F.length("hcpcs_cd") > 0))
)

# Convert AVG allowed -> estimated total allowed for this provider-hcpcs row
pb = pb.withColumn(
    "allowed_amt",
    F.when(F.col("avg_allowed").isNotNull() & F.col("tot_srvcs").isNotNull(),
           F.col("avg_allowed") * F.col("tot_srvcs"))
     .otherwise(F.lit(0.0))
)

pb_tot = (
    pb.groupBy("npi", "year")
    .agg(
        F.sum("allowed_amt").alias("total_allowed_amt"),
        F.sum("tot_srvcs").alias("total_services"),
        F.first("pb_state", ignorenulls=True).alias("pb_state"),
        F.first("pb_city", ignorenulls=True).alias("pb_city"),
        F.first("pb_zip5", ignorenulls=True).alias("pb_zip5"),
        F.first("pb_taxonomy", ignorenulls=True).alias("pb_taxonomy"),
    )
    .withColumn("pb_zip3", zip5_to_zip3("pb_zip5"))
    .withColumn(
        "allowed_per_service",
        F.when(F.col("total_services") > 0, F.col("total_allowed_amt") / F.col("total_services"))
         .otherwise(F.lit(None))
    )
)

top_hcpcs = (
    pb.groupBy("hcpcs_cd")
    .agg(F.sum("allowed_amt").alias("g_allowed"))
    .orderBy(F.desc("g_allowed"))
    .limit(TOPK_HCPCS)
    .select("hcpcs_cd")
)

pb_f = (
    pb.join(top_hcpcs, on="hcpcs_cd", how="inner")
      .join(pb_tot.select("npi", "year", "total_allowed_amt"), on=["npi", "year"], how="inner")
      .withColumn(
          "allowed_share_of_provider",
          F.when(F.col("total_allowed_amt") > 0, F.col("allowed_amt") / F.col("total_allowed_amt"))
           .otherwise(F.lit(0.0)),
      )
)

pb_features = (
    pb_f.select(
        "npi",
        "year",
        F.concat(F.lit("B:ALLOW_SHARE:"), F.col("hcpcs_cd")).alias("feature_id"),
        F.col("allowed_share_of_provider").alias("value"),
    )
)

# ---------------------------
# PART D: provider_drugs (long-form) + pd_unified scalars
# ---------------------------
drug_col = PD_GENERIC if DRUG_KEY == "generic" else PD_BRAND

pd = (
    pd_raw
    .withColumn("npi", norm_npi(PD_NPI))
    .select(
        "npi",
        "year",
        F.col(drug_col).alias("drug_id"),
        F.col(PD_COST).cast("double").alias("drug_cost"),
        F.col(PD_CLAIMS).cast("double").alias("drug_claims"),
        F.col(PD_STATE).alias("pd_state"),
        F.col(PD_CITY).alias("pd_city"),
        F.col(PD_TAXON).alias("pd_taxonomy"),
    )
    .filter(F.col("npi").isNotNull() & (F.length("npi") == 10))
    .filter(F.col("drug_id").isNotNull() & (F.length("drug_id") > 0))
)

pd_tot = (
    pd.groupBy("npi", "year")
    .agg(
        F.sum("drug_cost").alias("total_drug_cost"),
        F.sum("drug_claims").alias("total_drug_claims"),
        F.first("pd_state", ignorenulls=True).alias("pd_state"),
        F.first("pd_city", ignorenulls=True).alias("pd_city"),
        F.first("pd_taxonomy", ignorenulls=True).alias("pd_taxonomy"),
    )
    .withColumn(
        "cost_per_claim",
        F.when(F.col("total_drug_claims") > 0, F.col("total_drug_cost") / F.col("total_drug_claims"))
         .otherwise(F.lit(None))
    )
)

top_drugs = (
    pd.groupBy("drug_id")
    .agg(F.sum("drug_cost").alias("g_cost"))
    .orderBy(F.desc("g_cost"))
    .limit(TOPK_DRUGS)
    .select("drug_id")
)

pd_f = (
    pd.join(top_drugs, on="drug_id", how="inner")
      .join(pd_tot.select("npi", "year", "total_drug_cost"), on=["npi", "year"], how="inner")
      .withColumn(
          "cost_share_of_provider",
          F.when(F.col("total_drug_cost") > 0, F.col("drug_cost") / F.col("total_drug_cost"))
           .otherwise(F.lit(0.0)),
      )
)

pd_features = (
    pd_f.select(
        "npi",
        "year",
        F.concat(F.lit("D:COST_SHARE:"), F.col("drug_id")).alias("feature_id"),
        F.col("cost_share_of_provider").alias("value"),
    )
)

# ---------------------------
# Unified provider scalars (coalesce PB/PD + NPPES for geo fallback)
# ---------------------------
unified = (
    pb_tot.alias("b")
    .join(pd_tot.alias("d"), on=["npi", "year"], how="full")
    .select(
        F.coalesce(F.col("b.npi"), F.col("d.npi")).alias("npi"),
        F.coalesce(F.col("b.year"), F.col("d.year")).alias("year"),

        # Prefer Part B geo; fallback to Part D city/state; then NPPES
        F.coalesce(F.col("b.pb_state"), F.col("d.pd_state")).alias("state"),
        F.coalesce(F.col("b.pb_city"), F.col("d.pd_city")).alias("city"),
        F.col("b.pb_zip5").alias("zip5"),
        F.col("b.pb_zip3").alias("zip3"),

        # Prefer CMS provider type; fallback to PD specialty; keep NPPES taxonomy code separately
        F.coalesce(F.col("b.pb_taxonomy"), F.col("d.pd_taxonomy")).alias("cms_taxonomy"),

        F.col("b.total_allowed_amt"),
        F.col("b.total_services"),
        F.col("b.allowed_per_service"),
        F.col("d.total_drug_cost"),
        F.col("d.total_drug_claims"),
        F.col("d.cost_per_claim"),
    )
    .join(np, on="npi", how="left")
    .withColumn("zip5", F.coalesce(F.col("zip5"), F.col("nppes_zip5")))
    .withColumn("zip3", F.coalesce(F.col("zip3"), zip5_to_zip3("zip5")))
    .withColumn("state", F.coalesce(F.col("state"), F.col("nppes_state")))
    .withColumn("city", F.coalesce(F.col("city"), F.col("nppes_city")))
)

# ---------------------------
# Write Parquet (partitioned)
# ---------------------------
(pb_features
 .write.mode("overwrite")
 .partitionBy("year")
 .parquet(OUT_S3 + "provider_hcpcs/"))

(pd_features
 .write.mode("overwrite")
 .partitionBy("year")
 .parquet(OUT_S3 + "provider_drugs/"))

(unified
 .write.mode("overwrite")
 .partitionBy("year")
 .parquet(OUT_S3 + "provider_unified/"))
