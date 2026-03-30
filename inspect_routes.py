from backend.main import app
for route in app.routes:
    print(f"{route.path} [{route.methods if hasattr(route, 'methods') else 'N/A'}]")
