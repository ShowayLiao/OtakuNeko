import httpx

async def test_collections_api():
    base_url = "http://localhost:8000/api/v1/collections"
    
    # Test 1: Get collections list
    print("Test 1: GET /collections/")
    response = httpx.get(f"{base_url}/?username=hacci&limit=1")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Total: {data.get('total')}")
        if data.get('items'):
            item = data['items'][0]
            print(f"Subject ID: {item.get('subject_id')}")
            print(f"Updated at: {item.get('updated_at')}")
            print(f"Updated at type: {type(item.get('updated_at'))}")
            print(f"Status: {item.get('status')}")
    else:
        print(f"Error: {response.text}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: Get collection detail
    print("Test 2: GET /collections/7")
    response = httpx.get(f"{base_url}/7?username=hacci")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Subject ID: {data.get('subject_id')}")
        print(f"Status: {data.get('status')}")
        print(f"Updated at: {data.get('updated_at')}")
        print(f"Updated at type: {type(data.get('updated_at'))}")
    else:
        print(f"Error: {response.text}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 3: Update collection
    print("Test 3: PATCH /collections/7")
    update_data = {
        "rate": 8
    }
    response = httpx.patch(f"{base_url}/7", json=update_data)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Subject ID: {data.get('subject_id')}")
        print(f"Rate: {data.get('rate')}")
        print(f"Updated at: {data.get('updated_at')}")
        print(f"Updated at type: {type(data.get('updated_at'))}")
    else:
        print(f"Error: {response.text}")

if __name__ == '__main__':
    import asyncio
    asyncio.run(test_collections_api())
