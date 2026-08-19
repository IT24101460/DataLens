import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import random
from datetime import datetime, timedelta

def main():
    load_dotenv()

    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return

    print(f"Connecting to: {DATABASE_URL}")

    # Create a connection engine to Supabase
    engine = create_engine(DATABASE_URL)

    # Example dummy data injection using Pandas for 'employees'
    df_employees = pd.DataFrame({
        'id': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'name': [
            'Alice Smith', 'Bob Johnson', 'Charlie Brown', 'Diana Prince', 'Evan Wright',
            'Fiona Gallagher', 'George Miller', 'Hannah Abbott', 'Ian Somerhalder', 'Jane Doe'
        ],
        'department': [
            'Sales', 'Engineering', 'Marketing', 'HR', 'Sales',
            'Engineering', 'Finance', 'Marketing', 'Sales', 'HR'
        ],
        'role': [
            'Manager', 'Developer', 'Specialist', 'Manager', 'Specialist',
            'Developer', 'Analyst', 'Director', 'Specialist', 'Specialist'
        ],
        'salary': [
            85000.0, 95000.0, 70000.0, 82000.0, 65000.0,
            98000.0, 78000.0, 110000.0, 67000.0, 62000.0
        ],
        'hire_date': [
            '2021-03-15', '2022-01-10', '2020-11-20', '2019-06-05', '2023-02-18',
            '2021-08-30', '2022-05-12', '2018-09-01', '2023-07-22', '2020-04-14'
        ]
    })

    print("Pushing employees data to Supabase...")
    df_employees.to_sql('employees', con=engine, if_exists='replace', index=False)
    print("Successfully uploaded employees data to Supabase!")

    # Example dummy data for 'sales'
    regions = ['North America', 'Europe', 'Asia', 'South America', 'Australia']
    sales_data = []

    start_date = datetime.strptime('2023-01-01', '%Y-%m-%d')
    for i in range(1, 16):  # Insert 15 sales records
        emp_id = random.randint(1, 10)
        amount = round(random.uniform(500.0, 5000.0), 2)
        region = random.choice(regions)
        random_days = random.randint(0, 365)
        sale_date = (start_date + timedelta(days=random_days)).strftime('%Y-%m-%d')
        sales_data.append({'id': i, 'employee_id': emp_id, 'amount': amount, 'region': region, 'sale_date': sale_date})

    df_sales = pd.DataFrame(sales_data)

    print("Pushing sales data to Supabase...")
    df_sales.to_sql('sales', con=engine, if_exists='replace', index=False)
    print("Successfully uploaded sales data to Supabase!")

if __name__ == "__main__":
    main()
