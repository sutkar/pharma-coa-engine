import os

class Config:
    ENV = os.getenv("ENV", "development")
    MAX_FILE_SIZE_MB = 10
    ALLOWED_EXTENSIONS = ["pdf"]
    TARGET_PARAMETERS = [
        "Description", "Appearance", "Assay", "Purity", 
        "Loss on Drying", "Moisture Content", "Heavy Metals", 
        "Residue on Ignition", "pH", "Melting Point", 
        "Microbial Limit", "Impurity A", "Related Substances"
    ]