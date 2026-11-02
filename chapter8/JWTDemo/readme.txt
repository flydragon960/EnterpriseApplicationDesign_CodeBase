========================================================================
                     FLASK JWT AUTHENTICATION DEMO
========================================================================

A lightweight, minimalist example demonstrating stateless user authentication 
using Flask and PyJWT. This project showcases how to issue JSON Web Tokens (JWT) 
upon login and protect API endpoints using a custom decorator.

------------------------------------------------------------------------
1. PREREQUISITES
------------------------------------------------------------------------
Make sure you have Python 3.8+ installed on your system. 
Verify your installation:

    python3 --version  (or "python --version" on Windows)

------------------------------------------------------------------------
2. VIRTUAL ENVIRONMENT SETUP
------------------------------------------------------------------------
It is best practice to run Python applications inside an isolated virtual 
environment to prevent dependency conflicts.

Step A: Create the Virtual Environment
Navigate to your project directory and run:

    * On macOS / Linux:
        python3 -m venv venv

    * On Windows:
        python -m venv venv

Step B: Activate the Virtual Environment

    * On macOS / Linux:
        source venv/bin/activate

    * On Windows (Command Prompt):
        venv\Scripts\activate.bat

    * On Windows (PowerShell):
        venv\Scripts\Activate.ps1

(Your command prompt should now show "(venv)" at the beginning of the line.)

Step C: Install Dependencies
With the virtual environment active, run:

    pip install Flask PyJWT

------------------------------------------------------------------------
3. RUNNING THE APPLICATION
------------------------------------------------------------------------
1. Ensure your virtual environment is active.
2. Launch the Flask development server:

    python app.py

3. The application will start running at:
   http://127.0.0.1:5000/

------------------------------------------------------------------------
4. API USAGE & TESTING
------------------------------------------------------------------------

--- STEP 1: Log In to Obtain a Token ---
Send a POST request with valid credentials (username: admin, password: secret):

cURL Command:
    curl -X POST http://127.0.0.1:5000/login ^
      -H "Content-Type: application/json" ^
      -d "{\"username\": \"admin\", \"password\": \"secret\"}"

Response Example:
    {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }

--- STEP 2: Access the Protected Endpoint ---
Pass the access_token in the Authorization header as a Bearer token:

cURL Command:
    curl -X GET http://127.0.0.1:5000/api/protected ^
      -H "Authorization: Bearer <YOUR_ACCESS_TOKEN_HERE>"

Response Example:
    {
      "message": "Access granted successfully!",
      "user_info": {
        "user_id": 101,
        "username": "admin",
        "role": "faculty"
      }
    }

------------------------------------------------------------------------
5. EXITING THE VIRTUAL ENVIRONMENT
------------------------------------------------------------------------
When you are finished testing, deactivate the virtual environment by running:

    deactivate

========================================================================