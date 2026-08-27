import pandas as pd
import sqlite3 

conn = sqlite3.connect("search_data_by_company_number.db")

df = pd.read_sql_query("SELECT office_name FROM search_data_by_company_number WHERE officer_id = 'GGIddMattEOnS2mAEuo4CLgihPQ'", con=conn)

print(df)