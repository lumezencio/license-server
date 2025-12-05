import requests

# Login
login_response = requests.post(
    "http://localhost:8080/api/auth/login",
    json={"email": "admin@license-server.com", "password": "admin123"}
)
print("Login Response:", login_response.status_code)
print(login_response.json())

if login_response.status_code == 200:
    token = login_response.json().get("access_token")

    # Get licenses
    headers = {"Authorization": f"Bearer {token}"}
    licenses_response = requests.get(
        "http://localhost:8080/api/licenses",
        headers=headers
    )
    print("\nLicenses Response:", licenses_response.status_code)
    print(licenses_response.json())
