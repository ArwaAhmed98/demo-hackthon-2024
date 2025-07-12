from flask_csp import csp

csp_policy = {
    "default-src": "'self'",
    "script-src": ["'self'", "'https://fonts.googleapis.com'"],
    "style-src": ["'self'", "'https://fonts.googleapis.com'"],
    "img-src": ["'self'", "'data'", "'https://www.google-analytics.com'"],
}

app.config['CSP_HEADER'] = True
