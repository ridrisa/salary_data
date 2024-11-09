from flask import Flask, render_template, request, jsonify, send_file, make_response, url_for
from google.cloud import bigquery
from google.oauth2 import service_account
from sshtunnel import SSHTunnelForwarder
import psycopg2
import csv
import io
import logging
import pdfkit
import calendar
from datetime import datetime, date, timedelta
import re
import os

app = Flask(__name__)

# Configure Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)

# Google BigQuery Configuration
project_id = "looker-barqdata-2030"
google_credentials_path = "google_key.json"  # Ensure this path is correct

# Ensure the credentials file exists
if not os.path.exists(google_credentials_path):
    logging.error(f"Google credentials file not found at {google_credentials_path}")
    raise FileNotFoundError(f"Google credentials file not found at {google_credentials_path}")

credentials = service_account.Credentials.from_service_account_file(google_credentials_path)
client = bigquery.Client(credentials=credentials, project=project_id)

# PDFKit configuration
pdfkit_config = pdfkit.configuration(wkhtmltopdf='/usr/local/bin/wkhtmltopdf')  # Update this path as needed

# PostgreSQL SSH Tunnel Configuration
ssh_config = {
    "TunnelHost": "ec2-15-185-34-214.me-south-1.compute.amazonaws.com",
    "TunnelPort": 22,
    "TunnelUsername": "ramiz",
    "SSHKeyPath": "new.pem"  # Ensure this path is correct
}

# PostgreSQL DB Configuration
db_config = {
    "Host": "barqfleet-db-prod-stack-read-replica.cgr02s6xqwhy.me-south-1.rds.amazonaws.com",
    "Port": 5432,
    "MaintenanceDB": "barqfleet_db",
    "Username": "ventgres",
    "Password": "Jk56tt4HkzePFfa3ht",
    "sslmode": "prefer",
    "connect_timeout": 10
}

def configure_postgresql():
    """
    Establishes an SSH tunnel and connects to the PostgreSQL database.
    Returns the connection and tunnel objects.
    """
    try:
        tunnel = SSHTunnelForwarder(
            (ssh_config["TunnelHost"], ssh_config["TunnelPort"]),
            ssh_username=ssh_config["TunnelUsername"],
            ssh_pkey=ssh_config["SSHKeyPath"],
            remote_bind_address=(db_config["Host"], db_config["Port"]),
            logger=logging.getLogger("sshtunnel")
        )
        tunnel.start()
        logging.debug(f"SSH tunnel established. Local bind port: {tunnel.local_bind_port}")

        conn = psycopg2.connect(
            dbname=db_config["MaintenanceDB"],
            user=db_config["Username"],
            password=db_config["Password"],
            host='127.0.0.1',
            port=tunnel.local_bind_port,
            sslmode=db_config["sslmode"],
            connect_timeout=db_config["connect_timeout"]
        )
        logging.debug("Connected to the PostgreSQL database successfully.")
        return conn, tunnel
    except Exception as e:
        logging.error(f"Failed to connect to PostgreSQL: {e}")
        return None, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/postgresql')
def postgresql_page():
    return render_template('postgresql.html')

@app.route('/salaries', methods=['GET', 'POST'])
def salaries_route():
    if request.method == 'POST':
        month = request.form.get('month')
        year = request.form.get('year')

        if not month or not year:
            error_message = "Month and Year are required."
            # Check if the request is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Return the error message as JSON
                return jsonify({'error': error_message}), 400
            else:
                return render_template('salaries.html', error=error_message, calendar=calendar)

        # Calculate the start and end dates for the selected period
        start_date = datetime(int(year), int(month), 15)
        next_month = int(month) % 12 + 1
        next_year = int(year) + (1 if next_month == 1 else 0)
        end_date = datetime(next_year, next_month, 14)

        start_period = start_date.strftime('%Y-%m-%d')
        end_period = end_date.strftime('%Y-%m-%d')

        # Query for fetching salaries data from BigQuery
        query = """
        WITH CurrentPeriod AS (
            SELECT
                @start_period AS StartPeriod,
                @end_period AS EndPeriod
        )
        SELECT
            u.BARQ_ID,
            u.joining_date,
            u.id_number,
            u.Name,
            u.Status,
            u.Sponsorshipstatus,
            u.PROJECT,
            u.Supervisor,
            SUM(u.total_Orders) AS Total_Orders,
            SUM(u.Total_revenue) AS Total_Revenue,
            SUM(u.Gas_Usage_without_vat) AS Gas_Usage,
            CASE
                WHEN u.Sponsorshipstatus = 'Ajeer' THEN t.Ajeer
                WHEN u.PROJECT = 'Ecommerce' THEN t.Ecommerce
                WHEN u.PROJECT = 'Food' AND u.Sponsorshipstatus = 'Trial' THEN t.Food_Trial
                WHEN u.PROJECT = 'Food' AND u.Sponsorshipstatus = 'Inhouse' THEN t.Food_Inhouse
                WHEN u.PROJECT = 'Motorcycle' THEN t.motorcycle
            END AS target
        FROM
            master_saned.ultimate AS u
        LEFT JOIN
            master_saned.targets AS t ON EXTRACT(DAY FROM DATE(@end_period)) = t.Day
        WHERE
            u.Date BETWEEN (SELECT StartPeriod FROM CurrentPeriod) AND (SELECT EndPeriod FROM CurrentPeriod)
            AND u.Sponsorshipstatus = 'Ajeer'
        GROUP BY
            u.BARQ_ID,
            u.joining_date,
            u.id_number,
            u.Name,
            u.Status,
            u.Sponsorshipstatus,
            u.PROJECT,
            u.Supervisor,
            target
        """

        try:
            query_job = client.query(query, job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("start_period", "DATE", start_period),
                    bigquery.ScalarQueryParameter("end_period", "DATE", end_period),
                ]
            ))

            results = [dict(row) for row in query_job.result()]

            # Calculate salaries, bonuses, and gas usage
            for result in results:
                target = result['target'] or 0
                total_orders = result['Total_Orders'] or 0
                gas_usage = result['Gas_Usage'] or 0

                # Basic Salary Calculation
                basic_salary = (target / 13.333333333333334) * 53.3333333334 if target != 0 else 0
                result['Basic_Salary'] = basic_salary

                # Gas Deserved Calculation
                gas_deserved = min((target / 13.33) * 27.53, 2.065 * total_orders) if target != 0 else 0
                result['Gas_Deserved'] = gas_deserved

                # Deduct gas difference if Gas Usage is more than Gas Deserved
                gas_difference = max(0, gas_usage - gas_deserved)
                result['Gas_Difference'] = gas_difference

                # Bonus Calculation
                bonus_orders = total_orders - target
                if bonus_orders <= 0:
                    bonus_amount = bonus_orders * 10 - gas_difference
                elif bonus_orders <= 199:
                    bonus_amount = bonus_orders * 6
                elif 199 < bonus_orders <= 299:
                    bonus_amount = (199 * 6) + ((bonus_orders - 199) * 7)
                elif 299 < bonus_orders <= 399:
                    bonus_amount = (199 * 6) + (100 * 7) + ((bonus_orders - 299) * 8)
                else:
                    bonus_amount = (199 * 6) + (100 * 7) + (100 * 8) + ((bonus_orders - 399) * 9)

                result['Bonus_Amount'] = bonus_amount

                # Net Salary Calculation
                net_salary = basic_salary + bonus_amount - gas_difference
                result['Net_Salary'] = net_salary

        except Exception as e:
            logging.error(f"Error executing BigQuery: {e}")
            error_message = "Failed to execute the query. Please try again."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': error_message}), 500
            else:
                return render_template('salaries.html', error=error_message, calendar=calendar)

        # Check if the request is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Render only the results section
            return render_template('salaries_results.html', results=results, start_period=start_period, end_period=end_period)
        else:
            # Render the full page
            return render_template('salaries.html', results=results, start_period=start_period, end_period=end_period, calendar=calendar)

    # For GET requests
    return render_template('salaries.html', calendar=calendar)

@app.route('/get_tables')
def get_tables():
    """
    Retrieves the list of tables from the BigQuery dataset 'master_saned'.
    """
    try:
        dataset_ref = client.dataset("master_saned")
        tables = client.list_tables(dataset_ref)
        table_names = [table.table_id for table in tables]
        logging.debug(f"Retrieved {len(table_names)} tables from BigQuery.")
        return jsonify(table_names)
    except Exception as e:
        logging.error(f"Error fetching BigQuery tables: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_columns')
def get_columns():
    """
    Retrieves the list of columns for a specified table in the BigQuery dataset 'master_saned'.
    """
    table_name = request.args.get('table')
    if table_name:
        try:
            table_ref = client.dataset("master_saned").table(table_name)
            table = client.get_table(table_ref)
            column_names = [field.name for field in table.schema]
            logging.debug(f"Retrieved {len(column_names)} columns from table '{table_name}'.")
            return jsonify(column_names)
        except Exception as e:
            logging.error(f"Error fetching columns for table '{table_name}': {e}")
            return jsonify({"error": str(e)}), 500
    logging.warning("Table name not provided in '/get_columns' request.")
    return jsonify({"error": "Table name is required"}), 400

@app.route('/get_postgresql_tables')
def get_postgresql_tables_api():
    """
    API endpoint that returns the list of PostgreSQL tables in JSON format.
    """
    conn, tunnel = configure_postgresql()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name;
                """)
                tables = [row[0] for row in cur.fetchall()]
                logging.debug(f"Retrieved {len(tables)} tables from PostgreSQL.")
                return jsonify(tables)
        except Exception as e:
            logging.error(f"Error fetching PostgreSQL tables: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
            tunnel.stop()
            logging.debug("PostgreSQL connection and SSH tunnel closed.")
    else:
        logging.error("Failed to establish PostgreSQL connection.")
        return jsonify({"error": "Failed to connect to PostgreSQL"}), 500

@app.route('/get_postgresql_columns')
def get_postgresql_columns():
    """
    Retrieves the list of columns for a specified table in the PostgreSQL database.
    """
    table_name = request.args.get('table')
    if table_name:
        conn, tunnel = configure_postgresql()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = %s
                        ORDER BY ordinal_position;
                    """, (table_name,))
                    columns = [row[0] for row in cur.fetchall()]
                    logging.debug(f"Retrieved {len(columns)} columns from table '{table_name}'.")
                    return jsonify(columns)
            except Exception as e:
                logging.error(f"Error fetching columns for table '{table_name}': {e}")
                return jsonify({"error": str(e)}), 500
            finally:
                conn.close()
                tunnel.stop()
                logging.debug("PostgreSQL connection and SSH tunnel closed.")
        else:
            logging.error("Failed to establish PostgreSQL connection.")
            return jsonify({"error": "Failed to connect to PostgreSQL"}), 500
    logging.warning("Table name not provided in '/get_postgresql_columns' request.")
    return jsonify({"error": "Table name is required"}), 400

def is_valid_identifier(name):
    return re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name) is not None

@app.route('/execute_query', methods=['POST'])
def execute_query():
    """
    Executes a SELECT query on a specified BigQuery table with selected columns and an optional limit.
    """
    data = request.get_json()
    table_name = data.get('table')
    columns = data.get('columns')
    limit = data.get('limit')

    if not table_name or not columns:
        logging.warning("Table name or columns not provided in '/execute_query' request.")
        return jsonify({"error": "Table name and columns are required"}), 400

    try:
        # Safeguard against SQL injection by validating table and column names
        if not is_valid_identifier(table_name):
            raise ValueError("Invalid table name.")
        for col in columns:
            if not is_valid_identifier(col):
                raise ValueError(f"Invalid column name: {col}")

        # Construct the query
        query = f"SELECT {', '.join([f'`{col}`' for col in columns])} FROM `master_saned.{table_name}`"
        if limit and str(limit).isdigit():
            query += f" LIMIT {int(limit)}"

        logging.debug(f"Executing BigQuery: {query}")
        query_job = client.query(query)
        results = [dict(row) for row in query_job.result()]
        logging.debug(f"Retrieved {len(results)} rows from BigQuery.")
        return jsonify(results)
    except Exception as e:
        logging.error(f"Error executing BigQuery: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/execute_postgresql_query', methods=['POST'])
def execute_postgresql_query():
    """
    Executes a SELECT query on a specified PostgreSQL table with selected columns and an optional limit.
    """
    data = request.get_json()
    table_name = data.get('table')
    columns = data.get('columns')
    limit = data.get('limit')

    if not table_name or not columns:
        logging.warning("Table name or columns not provided in '/execute_postgresql_query' request.")
        return jsonify({"error": "Table name and columns are required"}), 400

    conn, tunnel = configure_postgresql()
    if conn:
        try:
            with conn.cursor() as cur:
                # Safeguard against SQL injection by using parameterized queries
                column_list = ', '.join([f'"{col}"' for col in columns])
                if not is_valid_identifier(table_name):
                    raise ValueError("Invalid table name.")
                for col in columns:
                    if not is_valid_identifier(col):
                        raise ValueError(f"Invalid column name: {col}")
                query = f"SELECT {column_list} FROM \"{table_name}\""
                if limit and str(limit).isdigit():
                    query += f" LIMIT %s"
                    cur.execute(query, (int(limit),))
                else:
                    cur.execute(query)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in rows]
                logging.debug(f"Retrieved {len(results)} rows from PostgreSQL.")
                return jsonify(results)
        except Exception as e:
            logging.error(f"Error executing PostgreSQL query: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
            tunnel.stop()
            logging.debug("PostgreSQL connection and SSH tunnel closed.")
    else:
        logging.error("Failed to establish PostgreSQL connection.")
        return jsonify({"error": "Failed to connect to PostgreSQL"}), 500

@app.route('/execute_custom_query', methods=['POST'])
def execute_custom_query():
    """
    Executes a custom query on either BigQuery or PostgreSQL based on the 'source' parameter.
    """
    data = request.get_json()
    query = data.get('query')
    source = data.get('source')

    if not query or not source:
        logging.warning("Query or source not provided in '/execute_custom_query' request.")
        return jsonify({"error": "Query and source are required"}), 400

    try:
        if source == 'bigquery':
            logging.debug(f"Executing custom BigQuery: {query}")
            query_job = client.query(query)
            results = [dict(row) for row in query_job.result()]
            logging.debug(f"Retrieved {len(results)} rows from BigQuery.")
        elif source == 'postgresql':
            conn, tunnel = configure_postgresql()
            if conn:
                try:
                    with conn.cursor() as cur:
                        logging.debug(f"Executing custom PostgreSQL query: {query}")
                        cur.execute(query)
                        if cur.description:
                            rows = cur.fetchall()
                            columns = [desc[0] for desc in cur.description]
                            results = [dict(zip(columns, row)) for row in rows]
                            logging.debug(f"Retrieved {len(results)} rows from PostgreSQL.")
                        else:
                            results = {"message": "Query executed successfully."}
                            logging.debug("Executed query that does not return rows.")
                finally:
                    conn.close()
                    tunnel.stop()
                    logging.debug("PostgreSQL connection and SSH tunnel closed.")
            else:
                raise ConnectionError("Failed to establish PostgreSQL connection.")
        else:
            logging.warning(f"Invalid source specified: {source}")
            return jsonify({"error": "Invalid source"}), 400
        return jsonify(results)
    except Exception as e:
        logging.error(f"Error executing custom query: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/download_csv', methods=['POST'])
def download_csv():
    """
    Executes a query on the specified source (BigQuery or PostgreSQL) and returns the results as a downloadable CSV file.
    """
    data = request.get_json()
    table_name = data.get('table')
    columns = data.get('columns')
    limit = data.get('limit')
    source = data.get('source')

    if not table_name or not columns or not source:
        logging.warning("Table name, columns, or source not provided in '/download_csv' request.")
        return jsonify({"error": "Table name, columns, and source are required"}), 400

    # Initialize CSV writer
    output = io.StringIO()
    writer = csv.writer(output)

    try:
        if source == 'bigquery':
            # Validate table and column names
            if not is_valid_identifier(table_name):
                raise ValueError("Invalid table name.")
            for col in columns:
                if not is_valid_identifier(col):
                    raise ValueError(f"Invalid column name: {col}")

            # Construct the query
            query = f"SELECT {', '.join([f'`{col}`' for col in columns])} FROM `master_saned.{table_name}`"
            if limit and str(limit).isdigit():
                query += f" LIMIT {int(limit)}"

            logging.debug(f"Executing BigQuery for CSV download: {query}")
            query_job = client.query(query)
            results = list(query_job.result())

            if results:
                # Write header
                writer.writerow(results[0].keys())
                # Write data rows
                for row in results:
                    writer.writerow(row.values())
                logging.debug(f"Retrieved and wrote {len(results)} rows from BigQuery to CSV.")
            else:
                logging.warning("No data fetched from BigQuery for CSV download.")

        elif source == 'postgresql':
            # Validate table and column names
            if not is_valid_identifier(table_name):
                raise ValueError("Invalid table name.")
            for col in columns:
                if not is_valid_identifier(col):
                    raise ValueError(f"Invalid column name: {col}")

            conn, tunnel = configure_postgresql()
            if conn:
                try:
                    with conn.cursor() as cur:
                        # Construct the query
                        column_list = ', '.join([f'"{col}"' for col in columns])
                        query = f"SELECT {column_list} FROM \"{table_name}\""
                        if limit and str(limit).isdigit():
                            query += f" LIMIT %s"
                            cur.execute(query, (int(limit),))
                        else:
                            cur.execute(query)
                        rows = cur.fetchall()
                        columns = [desc[0] for desc in cur.description]
                        if rows:
                            # Write header
                            writer.writerow(columns)
                            # Write data rows
                            for row in rows:
                                writer.writerow(row)
                            logging.debug(f"Retrieved and wrote {len(rows)} rows from PostgreSQL to CSV.")
                        else:
                            logging.warning("No data fetched from PostgreSQL for CSV download.")
                finally:
                    conn.close()
                    tunnel.stop()
                    logging.debug("PostgreSQL connection and SSH tunnel closed.")
            else:
                logging.error("Failed to establish PostgreSQL connection.")
                return jsonify({"error": "Failed to connect to PostgreSQL"}), 500
        else:
            logging.warning(f"Invalid source specified for CSV download: {source}")
            return jsonify({"error": "Invalid source"}), 400

        # Prepare CSV for download
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='query_results.csv'  # For Flask >=2.0
        )
    except Exception as e:
        logging.error(f"Error generating CSV: {e}")
        return jsonify({"error": str(e)}), 500
    
    
@app.route('/payslip', methods=['GET', 'POST'])
def payslip():
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        month = request.form.get('month')
        year = request.form.get('year')

        if not employee_id or not month or not year:
            error_message = "Employee ID, Month, and Year are required."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': error_message}), 400
            else:
                return render_template('payslip_form.html', error=error_message, calendar=calendar)

        try:
            employee_id = int(employee_id)
            month = int(month)
            year = int(year)
            # Fetch employee data and generate payslip
            return generate_payslip(employee_id, month, year)
        except ValueError:
            logging.error("Invalid input format.")
            error_message = "Invalid input format. Please enter correct values."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': error_message}), 400
            else:
                return render_template('payslip_form.html', error=error_message, calendar=calendar)
        except Exception as e:
            logging.error(f"Error generating payslip: {e}")
            error_message = "Failed to generate payslip."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': error_message}), 500
            else:
                return render_template('payslip_form.html', error=error_message, calendar=calendar)
    else:
        return render_template('payslip_form.html', calendar=calendar)
    

def generate_payslip(employee_id, month, year):
    # Calculate the start and end dates for the selected period
    start_date = datetime(year, month, 15)
    next_month = month % 12 + 1
    next_year = year + (1 if next_month == 1 else 0)
    end_date = datetime(next_year, next_month, 14)

    start_period = start_date.strftime('%Y-%m-%d')
    end_period = end_date.strftime('%Y-%m-%d')

    # Fetch employee data from BigQuery
    query = """
    WITH CurrentPeriod AS (
        SELECT
            @start_period AS StartPeriod,
            @end_period AS EndPeriod
    )
    SELECT
        u.BARQ_ID,
        u.joining_date,
        u.id_number,
        u.Name,
        u.Status,
        u.Sponsorshipstatus,
        u.PROJECT,
        u.Supervisor,
        SUM(u.total_Orders) AS Total_Orders,
        SUM(u.Total_revenue) AS Total_Revenue,
        SUM(u.Gas_Usage_without_vat) AS Gas_Usage,
        CASE
            WHEN u.Sponsorshipstatus = 'Ajeer' THEN t.Ajeer
            WHEN u.PROJECT = 'Ecommerce' THEN t.Ecommerce
            WHEN u.PROJECT = 'Food' AND u.Sponsorshipstatus = 'Trial' THEN t.Food_Trial
            WHEN u.PROJECT = 'Food' AND u.Sponsorshipstatus = 'Inhouse' THEN t.Food_Inhouse
            WHEN u.PROJECT = 'Motorcycle' THEN t.motorcycle
        END AS target
    FROM
        master_saned.ultimate AS u
    LEFT JOIN
        master_saned.targets AS t ON EXTRACT(DAY FROM DATE(@end_period)) = t.Day
    WHERE
        u.BARQ_ID = @employee_id
        AND u.Date BETWEEN (SELECT StartPeriod FROM CurrentPeriod) AND (SELECT EndPeriod FROM CurrentPeriod)
    GROUP BY
        u.BARQ_ID,
        u.joining_date,
        u.id_number,
        u.Name,
        u.Status,
        u.Sponsorshipstatus,
        u.PROJECT,
        u.Supervisor,
        target
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("employee_id", "INT64", employee_id),
            bigquery.ScalarQueryParameter("start_period", "DATE", start_period),
            bigquery.ScalarQueryParameter("end_period", "DATE", end_period),
        ]
    )
    query_job = client.query(query, job_config=job_config)
    results = [dict(row) for row in query_job.result()]

    if not results:
        raise Exception("Employee not found.")

    result = results[0]

    # Perform salary calculations
    target = result['target'] or 0
    total_orders = result['Total_Orders'] or 0
    gas_usage = result['Gas_Usage'] or 0

    # Basic Salary Calculation
    basic_salary = (target / 13.333333333333334) * 53.3333333334 if target != 0 else 0
    result['Basic_Salary'] = basic_salary

    # Gas Deserved Calculation
    gas_deserved = min((target / 13.33) * 27.53, 2.065 * total_orders) if target != 0 else 0
    result['Gas_Deserved'] = gas_deserved

    # Deduct gas difference if Gas Usage is more than Gas Deserved
    gas_difference = max(0, gas_usage - gas_deserved)
    result['Gas_Difference'] = gas_difference

    # Bonus Calculation
    bonus_orders = total_orders - target
    if bonus_orders <= 0:
        bonus_amount = bonus_orders * 10 - gas_difference
    elif bonus_orders <= 199:
        bonus_amount = bonus_orders * 6
    elif 199 < bonus_orders <= 299:
        bonus_amount = (199 * 6) + ((bonus_orders - 199) * 7)
    elif 299 < bonus_orders <= 399:
        bonus_amount = (199 * 6) + (100 * 7) + ((bonus_orders - 299) * 8)
    else:
        bonus_amount = (199 * 6) + (100 * 7) + (100 * 8) + ((bonus_orders - 399) * 9)

    result['Bonus_Amount'] = bonus_amount

    # Calculate Net Salary
    net_salary = basic_salary + bonus_amount - gas_difference
    result['Net_Salary'] = net_salary

    # Prepare the start and end period for the payslip
    start_period_display = start_date.strftime('%d %B %Y')
    end_period_display = end_date.strftime('%d %B %Y')

    # Render payslip template
    rendered = render_template(
        'payslip_template.html',
        result=result,
        net_salary=net_salary,
        start_period=start_period_display,
        end_period=end_period_display
    )

    # Generate PDF from rendered HTML
    pdf = pdfkit.from_string(rendered, False, configuration=pdfkit_config)

    # Send PDF as response
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=payslip.pdf'

    return response

if __name__ == "__main__":
    try:
        app.run(host='0.0.0.0', port=4000, debug=False)
    except Exception as e:
        logging.error(f"Failed to start Flask app: {e}")