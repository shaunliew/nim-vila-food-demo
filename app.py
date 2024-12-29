import streamlit as st
import requests
import os
from dotenv import load_dotenv
import tempfile

# Load environment variables
load_dotenv()

# Configure Streamlit page
st.set_page_config(
    page_title="Recipe Generator with NIM NVIDIA VILA",
    page_icon="🍳",
    layout="wide"
)

# Constants
INVOKE_URL = "https://ai.api.nvidia.com/v1/vlm/nvidia/vila"
NVCF_ASSET_URL = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
SUPPORTED_FORMATS = ["png", "jpg", "jpeg"]
SUPPORTED_MIMETYPES = {
    "png": ["image/png", "img"],
    "jpg": ["image/jpg", "img"],
    "jpeg": ["image/jpeg", "img"]
}

# Helper functions
def get_extension(filename):
    return os.path.splitext(filename)[1][1:].lower()

def mime_type(ext):
    return SUPPORTED_MIMETYPES[ext][0]

def media_type(ext):
    return SUPPORTED_MIMETYPES[ext][1]

def upload_asset(file_data, api_key):
    """Upload file to NVIDIA asset storage"""
    ext = get_extension(file_data.name)
    if ext not in SUPPORTED_FORMATS:
        st.error(f"Unsupported format. Please upload: {', '.join(SUPPORTED_FORMATS)}")
        return None

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp_file:
        tmp_file.write(file_data.getvalue())
        tmp_file_path = tmp_file.name

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    # Get upload URL
    authorize = requests.post(
        NVCF_ASSET_URL,
        headers=headers,
        json={"contentType": mime_type(ext), "description": "Recipe ingredient image"},
        timeout=30
    )
    authorize.raise_for_status()
    authorize_res = authorize.json()

    # Upload file
    with open(tmp_file_path, 'rb') as f:
        response = requests.put(
            authorize_res["uploadUrl"],
            data=f,
            headers={
                "x-amz-meta-nvcf-asset-description": "Recipe ingredient image",
                "content-type": mime_type(ext),
            },
            timeout=300
        )
    
    # Clean up temp file
    os.unlink(tmp_file_path)
    
    if response.status_code == 200:
        return authorize_res["assetId"]
    return None

def delete_asset(asset_id, api_key):
    """Delete asset from NVIDIA storage"""
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    response = requests.delete(
        f"{NVCF_ASSET_URL}/{asset_id}",
        headers=headers,
        timeout=30
    )
    response.raise_for_status()

def get_recipe_analysis(image_data, api_key):
    """Get recipe analysis from VILA"""
    # Upload image
    asset_id = upload_asset(image_data, api_key)
    if not asset_id:
        return None

    try:
        # Prepare query
        query = """
        Please analyze this cooking scene and provide:
        1. List all ingredients you can identify in the image
        2. Suggest a detailed recipe that could be made with these ingredients
        3. Provide step-by-step cooking instructions
        4. Explain any cultural significance of this dish
        5. Suggest 2-3 variations of this recipe
        Please be specific about quantities and cooking times where possible.
        """

        ext = get_extension(image_data.name)
        media_content = f'<{media_type(ext)} src="data:{mime_type(ext)};asset_id,{asset_id}" />'

        # Prepare API request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "NVCF-INPUT-ASSET-REFERENCES": asset_id,
            "NVCF-FUNCTION-ASSET-IDS": asset_id,
            "Accept": "application/json",
        }

        payload = {
            "max_tokens": 2048,
            "temperature": 0.7,
            "top_p": 0.7,
            "seed": 50,
            "messages": [{"role": "user", "content": f"{query} {media_content}"}],
            "stream": False,
            "model": "nvidia/vila",
        }

        # Get analysis
        response = requests.post(INVOKE_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        return result['choices'][0]['message']['content']
    
    finally:
        # Clean up
        if asset_id:
            delete_asset(asset_id, api_key)

def main():
    st.title("🍳 Recipe Generator with NIM NVIDIA VILA")
    st.write("Upload an image of ingredients or a cooking scene to get recipe suggestions!")

    # Get API key
    api_key = os.getenv("TEST_NVCF_API_KEY")
    if not api_key:
        st.error("Please set TEST_NVCF_API_KEY in your .env file")
        return

    # File uploader
    uploaded_file = st.file_uploader(
        "Choose an image",
        type=SUPPORTED_FORMATS,
        help="Upload an image of ingredients or a cooking scene"
    )

    if uploaded_file:
        # Display uploaded image
        col1, col2 = st.columns([1, 1])
        with col1:
            st.image(uploaded_file, caption="Uploaded Image", use_container_width=True)
        
        # Generate button
        if st.button("Generate Recipe"):
            with st.spinner("Analyzing image and generating recipe..."):
                recipe_analysis = get_recipe_analysis(uploaded_file, api_key)
                
                if recipe_analysis:
                    with col2:
                        st.markdown("### Recipe Analysis")
                        st.markdown(recipe_analysis)
                else:
                    st.error("Failed to generate recipe. Please try again.")

if __name__ == "__main__":
    main()