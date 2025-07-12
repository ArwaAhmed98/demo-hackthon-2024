from flask import Flask, make_response
app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers['X-Frame-Options'] = 'DENY'  # or SAMEORIGIN if needed
    return response

if __name__ == '__main__':
    app.run(debug=True)
