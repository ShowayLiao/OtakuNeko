import requests
from typing import Optional, Dict, Any


class AuthClient:
    """
    鉴权客户端类，用于测试后端API时处理登录和认证
    
    封装了登录逻辑，保存认证信息，提供已认证的HTTP请求方法
    """
    
    def __init__(self, base_url: str):
        """
        初始化鉴权客户端
        
        Args:
            base_url: 测试环境的基础URL，例如 "http://localhost:8000"
        """
        self.base_url = base_url
        self.token: Optional[str] = None
        self.user_info: Optional[Dict[str, Any]] = None
        self.session = requests.Session()
    
    def login(self, username: str, nickname: Optional[str] = None, 
              bangumi_id: Optional[int] = None, avatar_url: Optional[str] = None, 
              sign: Optional[str] = None) -> Dict[str, Any]:
        """
        登录或注册用户，并保存认证信息
        
        Args:
            username: 用户名
            nickname: 用户昵称（可选）
            bangumi_id: 第三方平台ID（可选）
            avatar_url: 头像图片URL（可选）
            sign: 用户签名/个性签名（可选）
        
        Returns:
            登录响应数据
        
        Raises:
            requests.HTTPError: 登录失败时抛出
        """
        login_url = f"{self.base_url}/api/v1/auth/login"
        
        # 构造登录请求数据
        login_data = {
            "username": username
        }
        
        # 添加可选参数
        if nickname is not None:
            login_data["nickname"] = nickname
        if bangumi_id is not None:
            login_data["bangumi_id"] = bangumi_id
        if avatar_url is not None:
            login_data["avatar_url"] = avatar_url
        if sign is not None:
            login_data["sign"] = sign
        
        # 发送登录请求
        response = self.session.post(login_url, json=login_data)
        response.raise_for_status()
        
        # 保存认证信息
        login_response = response.json()
        self.token = login_response["access_token"]
        self.user_info = login_response["user"]
        
        # 设置默认的Authorization头
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}"
        })
        
        return login_response
    
    def get_authenticated_client(self) -> requests.Session:
        """
        获取已认证的HTTP会话客户端
        
        Returns:
            已设置Authorization头的requests.Session对象
        
        Raises:
            ValueError: 未登录时抛出
        """
        if not self.token:
            raise ValueError("未登录，请先调用login方法获取token")
        
        return self.session
    
    def clear_auth(self) -> None:
        """
        清除认证信息
        """
        self.token = None
        self.user_info = None
        self.session.headers.pop("Authorization", None)
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """
        获取当前登录用户信息
        
        Returns:
            当前登录用户信息，未登录时返回None
        """
        return self.user_info
    
    def get_token(self) -> Optional[str]:
        """
        获取当前认证token
        
        Returns:
            当前认证token，未登录时返回None
        """
        return self.token
