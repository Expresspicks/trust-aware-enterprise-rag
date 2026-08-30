# Hybrid Trust-Aware Enterprise SQL-RAG Framework

This repository contains a proof-of-concept hybrid trust-aware enterprise retrieval framework. The system combines MySQL-based structured retrieval, PDF-based RAG retrieval, LLM query routing, role and region-based access checking, and CT-BT-ET trust scoring for controlled enterprise question answering.

## Project Purpose

The project was developed to evaluate whether an LLM can be used in a controlled enterprise-style retrieval workflow instead of being used as a standalone chatbot. The system routes each user question to structured retrieval, document retrieval, hybrid SQL-RAG retrieval, or safety handling before generating the final response.

## Main Features

- MySQL-based structured retrieval
- PDF-based RAG retrieval
- LLM-based query routing
- Role and region-based access checking
- Contextual Trust, Behavioural Trust, and Evidence Trust scoring
- Allow, Limit, and Deny response decisions
- 40-case functional evaluation support
- 500-scenario synthetic trust simulation

## Project Structure

```text
app.py                         Main Flask application
routes.py                      Application routes and response workflow
database.py                    Database connection helper
query_router.py                LLM-based query routing
sql_agent_graph.py             SQL retrieval workflow
sql_tools.py                   SQL helper functions
rag_service.py                 PDF-based RAG retrieval
trust/ct.py                    Contextual Trust calculation
trust/bt.py                    Behavioural Trust calculation
trust/et.py                    Evidence Trust calculation
trust_weight_simulation.py     500-scenario trust-weight simulation
trust_confusion_matrix.py      Trust confusion matrix calculation
database_schema.sql            MySQL database schema
datasets/                      CSV datasets used in the prototype
knowledgebase/Report.pdf       PDF knowledge source for RAG
templates/                     Flask HTML templates
static/                        CSS and JavaScript files
requirements.txt               Python package requirements
config.example.py              Safe example configuration file

Datasets
The prototype uses the following datasets:

datasets/finance_dataset.csv
datasets/amazon_access_train.csv
datasets/amazon_access_test.csv

The finance dataset is used for structured sales and customer-related questions. The Amazon Employee Access dataset is used as an 
external structured dataset for access-governance style questions.

The unstructured knowledge source is:

knowledgebase/Report.pdf

This PDF is used by the RAG module for document-based retrieval.

Installation

Clone the repository:

git clone https://github.com/Expresspicks/trust-aware-enterprise-rag.git
cd trust-aware-enterprise-rag

Create and activate a virtual environment:

python3 -m venv .venv
source .venv/bin/activate

Install the required packages:

pip install -r requirements.txt
Configuration

The real config.py file is not included in this repository because it contains local database credentials and API keys.

Create a local config file by copying the example file:

cp config.example.py config.py

Then open config.py and update the values:

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_mysql_password_here",
    "database": "main",
}

LLM_CONFIG = {
    "model": "openai/gpt-oss-120b",
    "api_key": "your_groq_api_key_here",
}
Database Setup

Create a MySQL database named:

main

Import the schema:

mysql -u root -p main < database_schema.sql

Then import the CSV datasets into the matching MySQL tables using MySQL Workbench or another MySQL import tool.

Required dataset files:

datasets/finance_dataset.csv
datasets/amazon_access_train.csv
datasets/amazon_access_test.csv
Running the Application

After setting up the database and configuration file, run:

python app.py

Then open the local Flask application in your browser.

Common local URL:

http://127.0.0.1:5000
Running the Trust Simulation

To run the synthetic trust-weight simulation:

python trust_weight_simulation.py

This script generates synthetic enterprise scenarios and evaluates the selected CT-BT-ET trust-weight formula.

Trust Formula

The prototype uses the following Total Trust formula:

TT = 0.4CT + 0.3BT + 0.3ET

where:

CT = Contextual Trust
BT = Behavioural Trust
ET = Evidence Trust

The trust decision is based on Allow, Limit, and Deny classes.

Reproducibility Notes

Important reproducibility settings:

LLM backend: openai/gpt-oss-120b through Groq API
Embedding model: all-MiniLM-L6-v2
RAG chunk size: 500 characters
RAG chunk overlap: 100 characters
FAISS index type: IndexFlatIP
Top-k retrieval: 3
Trust score scale: 0-100
Synthetic simulation seed: 42
Security Notice

The repository does not include real API keys, database passwords, virtual environment files, cache files, generated vector indexes, or local configuration files.

The following files are intentionally excluded:

config.py
.env
.venv/
__pycache__/
vectorstore/

A safe example configuration file is provided as:

config.example.py
