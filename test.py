import requests

API_KEY = "a77e1e1a-fa06-11f0-a6b2-0200cd936042"
PHONE_NUMBER = "9865206921"  # Include country code (India = 91)

def send_voice_otp(phone_number):
    url = f"https://2factor.in/API/V1/{API_KEY}/VOICE/{phone_number}/AUTOGEN"

    try:
        response = requests.get(url)
        data = response.json()

        if data["Status"] == "Success":
            print("OTP sent successfully via voice call!")
            print("Session ID:", data["Details"])
            return data["Details"]
        else:
            print("Failed to send OTP:", data)
            return None

    except Exception as e:
        print("Error:", str(e))
        return None

def send_voice_otp_2factor(phone, otp):
    """
    Sends OTP via Voice Call using 2factor.in API.
    """
    api_key = "a77e1e1a-fa06-11f0-a6b2-0200cd936042"
    # Clean phone number (remove +91 or spaces if needed, but 2factor mostly handles 10 digits)
    # Assuming Indian numbers for 2factor.in usually.
    # If phone has +91, we might keep it or strip it depending on API.
    # 2factor.in usually takes full number.
    
    url = f"https://2factor.in/API/V1/{api_key}/VOICE/{phone}/{otp}"
    
    try:
        response = requests.get(url)
        print(f"2Factor Voice Response: {response.text}")
        data = response.json()
        if data.get('Status') == 'Success':
            return True
        return False
    except Exception as e:
        print(f"Error sending Voice OTP: {e}")
        return False

# Example usage
# send_voice_otp(PHONE_NUMBER)
send_voice_otp_2factor(PHONE_NUMBER, 2323)
