import asyncio
import sys
sys.path.insert(0, '.')

from app.api.v1.auth import LoginRequest, LoginResponse
from app.core.security import create_access_token, decode_access_token

async def test_login_request():
    print("Testing LoginRequest schema...")
    
    # Test valid request with minimal fields
    try:
        valid_request = LoginRequest(username="testuser")
        print(f"✓ Valid LoginRequest created with minimal fields: {valid_request.username}")
    except Exception as e:
        print(f"✗ Failed to create LoginRequest: {e}")
        return False
    
    # Test valid request with all fields
    try:
        valid_request_full = LoginRequest(
            username="testuser2",
            nickname="Test User",
            bangumi_id=12345,
            avatar_url="http://example.com/avatar.jpg",
            sign="Hello World!"
        )
        print(f"✓ Valid LoginRequest created with all fields: {valid_request_full.username}")
    except Exception as e:
        print(f"✗ Failed to create LoginRequest with all fields: {e}")
        return False
    
    # Test request with extra fields (should fail)
    try:
        invalid_request = LoginRequest(username="testuser", extra_field="value")
        print(f"✗ LoginRequest should reject extra fields")
        return False
    except Exception as e:
        print(f"✓ LoginRequest correctly rejects extra fields: {type(e).__name__}")
    
    return True

async def test_login_response():
    print("\nTesting LoginResponse schema...")
    
    # Test valid response with new format
    try:
        token = create_access_token(data={"sub": "123", "username": "testuser"})
        user_info = {
            "id": 123,
            "username": "testuser",
            "nickname": "Test User",
            "email": None,
            "avatar_url": "http://example.com/avatar.jpg",
            "bangumi_id": 12345,
            "sign": "Hello World!",
            "created_at": "2023-01-01T00:00:00"
        }
        response = LoginResponse(
            access_token=token,
            token_type="bearer",
            user=user_info
        )
        print(f"✓ Valid LoginResponse created with new format")
        print(f"  - access_token: {response.access_token[:50]}...")
        print(f"  - token_type: {response.token_type}")
        print(f"  - user: {response.user['username']}")
    except Exception as e:
        print(f"✗ Failed to create LoginResponse: {e}")
        return False
    
    return True

async def test_jwt_flow():
    print("\nTesting JWT token flow...")
    
    # Test token creation
    try:
        token = create_access_token(data={"sub": "123", "username": "testuser"})
        print(f"✓ Token created: {token[:50]}...")
    except Exception as e:
        print(f"✗ Failed to create token: {e}")
        return False
    
    # Test token decoding
    try:
        decoded = decode_access_token(token)
        if decoded:
            print(f"✓ Token decoded successfully")
            print(f"  - sub: {decoded.get('sub')}")
            print(f"  - username: {decoded.get('username')}")
            print(f"  - exp: {decoded.get('exp')}")
        else:
            print(f"✗ Token decoding returned None")
            return False
    except Exception as e:
        print(f"✗ Failed to decode token: {e}")
        return False
    
    return True

async def test_no_password_logic():
    print("\nChecking for password-related logic...")
    
    import inspect
    from app.api.v1.auth import login
    
    source = inspect.getsource(login)
    
    # Check for password-related keywords
    password_keywords = ['password', 'verify_password', 'get_password_hash', 'bcrypt', 'pwd_context']
    found_password = False
    
    for keyword in password_keywords:
        if keyword.lower() in source.lower():
            print(f"✗ Found password-related keyword: {keyword}")
            found_password = True
    
    if not found_password:
        print(f"✓ No password-related logic found")
        return True
    
    return False

async def test_comprehensive_login_logic():
    print("\nChecking comprehensive login logic...")
    
    import inspect
    from app.api.v1.auth import login
    
    source = inspect.getsource(login)
    
    # Check for core logic components
    checks = [
        ('select(User).where(User.username == data.username)', "Uses SQLAlchemy select query for user lookup"),
        ('create_access_token', "Generates JWT token"),
        ('if user:', "Checks if user exists"),
        ('User(', "Creates new user when user doesn't exist"),
        ('data.nickname is not None', "Selectively updates nickname"),
        ('data.bangumi_id is not None', "Selectively updates bangumi_id"),
        ('data.avatar_url is not None', "Selectively updates avatar_url"),
        ('data.sign is not None', "Selectively updates sign"),
        ('update_fields', "Tracks if fields need updating"),
        ('await db.commit()', "Uses database transactions"),
    ]
    
    success = True
    for check_str, description in checks:
        if check_str in source:
            print(f"✓ {description}")
        else:
            print(f"✗ {description}")
            success = False
    
    return success

if __name__ == "__main__":
    print("=" * 60)
    print("Backend Auth Refactoring Verification Tests")
    print("=" * 60)
    
    success = True
    
    success &= asyncio.run(test_login_request())
    success &= asyncio.run(test_login_response())
    success &= asyncio.run(test_jwt_flow())
    success &= asyncio.run(test_no_password_logic())
    success &= asyncio.run(test_comprehensive_login_logic())
    
    print("\n" + "=" * 60)
    if success:
        print("✓ All verification tests passed!")
    else:
        print("✗ Some tests failed!")
    print("=" * 60)
