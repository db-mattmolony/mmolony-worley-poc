# Databricks notebook source
# MAGIC %md
# MAGIC # Create Unity Catalog Resources
# MAGIC
# MAGIC Idempotent setup of the catalog and schema used by the Worley Supervisor Agent.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE SCHEMA IF NOT EXISTS az_databricks_poc.multi_agent_supervisor;
