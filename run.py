# run.py
from app import create_app

# Create the Flask application using the factory pattern
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
