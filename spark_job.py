from pyspark.sql import SparkSession
from pyspark.sql.functions import col, array_intersect, size
from pymongo import MongoClient
import spacy
import os

# Initialize Spark session
spark = SparkSession.builder \
    .appName("JobMatching") \
    .config("spark.mongodb.input.uri", os.getenv('MONGO_URI')) \
    .config("spark.mongodb.output.uri", os.getenv('MONGO_URI')) \
    .master("local[*]") \
    .getOrCreate()

# Load custom model
nlp = spacy.load("./models/custom_model")

def extract_technologies(text):
    doc = nlp(text)
    return [ent.text.lower() for ent in doc.ents if ent.label_ == "TECH"]

def fetch_candidates():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["job_portal"]
    candidates = db.candidates.find({})
    return [candidate for candidate in candidates]

def match_candidates(job_description):
    technology_names = extract_technologies(job_description)

    # Load candidates data into a Spark DataFrame
    candidates_data = fetch_candidates()
    candidates_df = spark.createDataFrame(candidates_data)

    # Perform skill matching
    matched_candidates_df = candidates_df \
        .withColumn("matchedSkills", array_intersect(col("skills"), technology_names)) \
        .withColumn("matchedSkillCount", size(col("matchedSkills"))) \
        .filter(col("matchedSkillCount") > 0) \
        .orderBy(col("matchedSkillCount").desc())

    # Collect results as dictionary
    matched_candidates = matched_candidates_df.collect()
    return [{"name": row.name, "email": row.email, "skills": row.skills, "matchedSkills": row.matchedSkills} for row in matched_candidates]
