import asyncio
from app.services.bangumi_service import get_audience_feedback

async def test_get_audience_feedback():
    # 测试一个已知的 Bangumi ID，比如 "四月是你的谎言" 的 ID
    subject_id = 100444
    
    print(f"Testing get_audience_feedback with subject_id: {subject_id}")
    
    try:
        result = await get_audience_feedback(subject_id)
        print("\nTest result:")
        print(f"Type: {type(result)}")
        
        # 转成 dict
        result_dict = result.model_dump(exclude_none=True)
        print(f"Keys: {list(result_dict.keys())}")
        
        print(f"\nSubject ID: {result_dict.get('subject_id')}")
        
        # 测试 comments 字段
        comments = result_dict.get('comments', [])
        print(f"\nComments ({len(comments)}):")
        for i, comment in enumerate(comments[:3]):  # 只显示前3个评论
            print(f"{i+1}. {comment.get('content', '')[:100]}...")
        
        # 测试 reviews 字段
        reviews = result_dict.get('reviews', [])
        print(f"\nReviews ({len(reviews)}):")
        for i, review in enumerate(reviews):
            print(f"{i+1}. {review.get('title', '')}")
            print(f"   {review.get('summary', '')[:100]}...")
            
    except Exception as e:
        print(f"Test failed with error: {e}")

if __name__ == "__main__":
    asyncio.run(test_get_audience_feedback())
