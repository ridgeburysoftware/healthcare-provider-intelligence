resource "aws_glue_catalog_database" "cms_raw" {
  name = "cms_raw"
}

resource "aws_glue_catalog_database" "cms_derived" {
  name = "cms_derived"
}
