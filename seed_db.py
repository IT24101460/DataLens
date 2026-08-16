import sqlite3
import random
from datetime import datetime, timedelta

def main():
    # Connect to the SQLite database (this will create it if it doesn't exist)
    conn = sqlite3.connect('datalens_sandbox.db')
    cursor = conn.cursor()

    # Create 'employees' table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            role TEXT NOT NULL,
            salary REAL NOT NULL,
            hire_date TEXT NOT NULL
        )
    ''')

    # Create 'sales' table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            amount REAL NOT NULL,
            region TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        )
    ''')

    # Dummy data for employees
    employee_data = [
        ('Alice Smith', 'Sales', 'Manager', 85000.0, '2021-03-15'),
        ('Bob Johnson', 'Engineering', 'Developer', 95000.0, '2022-01-10'),
        ('Charlie Brown', 'Marketing', 'Specialist', 70000.0, '2020-11-20'),
        ('Diana Prince', 'HR', 'Manager', 82000.0, '2019-06-05'),
        ('Evan Wright', 'Sales', 'Specialist', 65000.0, '2023-02-18'),
        ('Fiona Gallagher', 'Engineering', 'Developer', 98000.0, '2021-08-30'),
        ('George Miller', 'Finance', 'Analyst', 78000.0, '2022-05-12'),
        ('Hannah Abbott', 'Marketing', 'Director', 110000.0, '2018-09-01'),
        ('Ian Somerhalder', 'Sales', 'Specialist', 67000.0, '2023-07-22'),
        ('Jane Doe', 'HR', 'Specialist', 62000.0, '2020-04-14')
    ]
    
    cursor.executemany('''
        INSERT INTO employees (name, department, role, salary, hire_date)
        VALUES (?, ?, ?, ?, ?)
    ''', employee_data)

    # Fetch inserted employee IDs
    cursor.execute('SELECT id FROM employees')
    employee_ids = [row[0] for row in cursor.fetchall()]

    # Dummy data for sales
    regions = ['North America', 'Europe', 'Asia', 'South America', 'Australia']
    sales_data = []
    
    start_date = datetime.strptime('2023-01-01', '%Y-%m-%d')
    for _ in range(15):  # Insert 15 sales records
        emp_id = random.choice(employee_ids)
        amount = round(random.uniform(500.0, 5000.0), 2)
        region = random.choice(regions)
        random_days = random.randint(0, 365)
        sale_date = (start_date + timedelta(days=random_days)).strftime('%Y-%m-%d')
        sales_data.append((emp_id, amount, region, sale_date))

    cursor.executemany('''
        INSERT INTO sales (employee_id, amount, region, sale_date)
        VALUES (?, ?, ?, ?)
    ''', sales_data)

    # Commit changes and close the connection
    conn.commit()
    conn.close()

    print("Database 'datalens_sandbox.db' and tables 'employees' and 'sales' were created and populated successfully with dummy data.")

if __name__ == "__main__":
    main()
