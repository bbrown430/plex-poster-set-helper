import requests

# Define the URL and payload
api_url = "http://localhost:8000/upload/url"
headers = {"Content-Type": "application/json"}
params = {"url": "https://mediux.pro/sets/9337"}

# Send the POST request
response = requests.post(api_url, headers=headers, params=params)

# Print the response
print("Status Code:", response.status_code)
print("Response:", response.text)
