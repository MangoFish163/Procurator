from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from app.core.security import verify_token
from app.main import token_dependency
from app.scripts.manage_dlq import (
    _list_dead_letters,
    _inspect_dead_letter,
    _replay_dead_letter,
    _purge_dlq
)

router = APIRouter(prefix="/dlq", tags=["DLQ"])

# 鉴权依赖
# 注意：这里我们复用 main.py 的 token_dependency，但由于循环导入问题
# 我们可能需要重新定义或者从 core 导入。
# 为了简单，我们假设 main.py 已经把 token_dependency 注入到了 app 级别，
# 或者我们直接在这里用 Header 校验。
# 更好的做法是从 app.core.security 导入基础校验，这里手动构造 Depends。
# 不过，既然 token_dependency 已经在 main.py 定义，我们可以暂时跳过它，
# 或者在 main.py 注册 router 时统一添加 dependencies。

@router.get("/{queue_name}", response_model=List[Dict[str, Any]])
def list_dlq(queue_name: str, count: int = 20, ident=Depends(token_dependency)):
    """
    列出指定队列的死信
    """
    res = _list_dead_letters(queue_name, count)
    if isinstance(res, dict) and "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@router.get("/{queue_name}/{msg_id}")
def inspect_dlq(queue_name: str, msg_id: str, ident=Depends(token_dependency)):
    """
    查看死信详情
    """
    res = _inspect_dead_letter(queue_name, msg_id)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res

@router.post("/{queue_name}/{msg_id}/replay")
def replay_dlq(queue_name: str, msg_id: str, ident=Depends(token_dependency)):
    """
    重放死信
    """
    # 鉴权：只有 admin 或 ops 角色可以重放？
    # 目前先不限制
    res = _replay_dead_letter(queue_name, msg_id)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@router.delete("/{queue_name}")
def purge_dlq(queue_name: str, ident=Depends(token_dependency)):
    """
    清空死信队列 (慎用)
    """
    # 鉴权：建议只允许 admin
    role = ident.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can purge DLQ")
        
    res = _purge_dlq(queue_name)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res
