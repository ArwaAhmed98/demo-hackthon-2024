from flask import Flask, make_response

app = Flask(__name__)

@app.after_request
def add_csp_header(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net/npm/bootstrap@4.6.0/dist/js/bootstrap.min.js; style-src 'self' https://fonts.googleapis.com; img-src 'self' data: https://via.placeholder.com/300x150; frame-src none;"
    return response

if __name__ == '__main__':
    app.run()
