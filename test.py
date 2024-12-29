import requests
import os
import uuid
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

invoke_url = "https://ai.api.nvidia.com/v1/vlm/nvidia/vila"
stream = False

# query to get comprehensive recipe analysis
query = """
Please analyze this cooking scene and provide:
1. List all ingredients you can identify in the image
2. Suggest a detailed recipe that could be made with these ingredients
3. Provide step-by-step cooking instructions
4. Explain any cultural significance of this dish
5. Suggest 2-3 variations of this recipe
Please be specific about quantities and cooking times where possible.
"""

# Define your image path here
IMAGE_PATH = "image2.png"  # Replace with your image path

kApiKey = os.getenv("TEST_NVCF_API_KEY")
if not kApiKey:
    raise ValueError("Please set TEST_NVCF_API_KEY in your .env file")

kNvcfAssetUrl = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
# ext: {mime, media}
kSupportedList = {
    "png": ["image/png", "img"],
    "jpg": ["image/jpg", "img"],
    "jpeg": ["image/jpeg", "img"],
    "mp4": ["video/mp4", "video"],
}

# [Previous helper functions remain the same]
def get_extention(filename):
    _, ext = os.path.splitext(filename)
    ext = ext[1:].lower()
    return ext

def mime_type(ext):
    return kSupportedList[ext][0]

def media_type(ext):
    return kSupportedList[ext][1]

def _upload_asset(media_file, description):
    ext = get_extention(media_file)
    assert ext in kSupportedList
    data_input = open(media_file, "rb")
    headers={
        "Authorization": f"Bearer {kApiKey}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    assert_url = kNvcfAssetUrl
    authorize = requests.post(
        assert_url,
        headers = headers,
        json={"contentType": f"{mime_type(ext)}", "description": description},
        timeout=30,
    )
    authorize.raise_for_status()

    authorize_res = authorize.json()
    response = requests.put(
        authorize_res["uploadUrl"],
        data=data_input,
        headers={
            "x-amz-meta-nvcf-asset-description": description,
            "content-type": mime_type(ext),
        },
        timeout=300,
    )

    response.raise_for_status()
    if response.status_code == 200:
        print(f"upload asset_id {authorize_res['assetId']} successfully!")
    else:
        print(f"upload asset_id {authorize_res['assetId']} failed.")
    return uuid.UUID(authorize_res["assetId"])

def _delete_asset(asset_id):
    headers = {
        "Authorization": f"Bearer {kApiKey}",
    }
    assert_url = f"{kNvcfAssetUrl}/{asset_id}"
    response = requests.delete(
        assert_url, headers=headers, timeout=30
    )
    response.raise_for_status()

def chat_with_media_nvcf(infer_url, media_files, query: str, stream: bool = False):
    asset_list = []
    ext_list = []
    media_content = ""
    assert isinstance(media_files, list), f"{media_files}"
    has_video = False
    for media_file in media_files:
        ext = get_extention(media_file)
        assert ext in kSupportedList, f"{media_file} format is not supported"
        if media_type(ext) == "video":
            has_video = True
        asset_id = _upload_asset(media_file, "Reference media file")
        asset_list.append(f"{asset_id}")
        ext_list.append(ext)
        media_content += f'<{media_type(ext)} src="data:{mime_type(ext)};asset_id,{asset_id}" />'
    if has_video:
        assert len(media_files) == 1, "Only single video supported."
    asset_seq = ",".join(asset_list)
    
    headers = {
        "Authorization": f"Bearer {kApiKey}",
        "Content-Type": "application/json",
        "NVCF-INPUT-ASSET-REFERENCES": asset_seq,
        "NVCF-FUNCTION-ASSET-IDS": asset_seq,
        "Accept": "application/json",
    }
    if stream:
        headers["Accept"] = "text/event-stream"

    messages = [
        {
            "role": "user",
            "content": f"{query} {media_content}",
        }
    ]
    payload = {
        "max_tokens": 1024,
        "temperature": 0.2,
        "top_p": 0.7,
        "seed": 50,
        "num_frames_per_inference": 8,
        "messages": messages,
        "stream": stream,
        "model": "nvidia/vila",
    }

    response = requests.post(infer_url, headers=headers, json=payload, stream=stream)
    if stream:
        for line in response.iter_lines():
            if line:
                print(line.decode("utf-8"))
    else:
        # Only print the description content
        result = response.json()
        print(result['choices'][0]['message']['content'])

    # Clean up assets
    for asset_id in asset_list:
        _delete_asset(asset_id)

if __name__ == "__main__":
    media_samples = [IMAGE_PATH]  # Use the defined image path
    chat_with_media_nvcf(invoke_url, media_samples, query, stream)