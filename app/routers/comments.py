from datetime import datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, auth
from app.database import get_db
from app.observability import observability, trace_function, get_logger

router = APIRouter()
logger = get_logger()

@router.post("/comments/", response_model=schemas.Comment, tags=["Comments"])
@trace_function("comment_creation")
async def create_comment(
        plant_id: int,
        comment: str,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Create a comment on a plant."""
    logger.info("Creating comment", plant_id=plant_id, user_id=current_user.id)

    plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
    if not plant:
        logger.error("Plant not found for comment", plant_id=plant_id)
        raise HTTPException(status_code=404, detail="Plant not found")

    db_comment = models.Comment(
        plant_id=plant_id,
        user_id=current_user.id,
        comment=comment,
        time_stamp=dt.now(),
    )

    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    observability.record_comment_creation()

    logger.info(
        "Comment created successfully",
        comment_id=db_comment.id,
        plant_id=plant_id,
        user_id=current_user.id
    )

    return db_comment

@router.get("/plants/{plant_id}/comments/", response_model=list[schemas.Comment], tags=["Comments"])
@trace_function("get_plant_comments")
async def get_plant_comments(
        plant_id: int,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Get all comments for a specific plant."""
    logger.info("Getting plant comments", plant_id=plant_id)

    plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
    if not plant:
        logger.error("Plant not found for comments", plant_id=plant_id)
        raise HTTPException(status_code=404, detail="Plant not found")

    comments = db.query(models.Comment).filter(models.Comment.plant_id == plant_id).all()

    logger.info("Plant comments retrieved", plant_id=plant_id, count=len(comments))
    return comments

@router.put("/comments/{comment_id}", response_model=schemas.Comment, tags=["Comments"])
@trace_function("comment_update")
async def update_comment(
        comment_id: int,
        comment_text: str,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Update a comment."""
    logger.info("Updating comment", comment_id=comment_id, user_id=current_user.id)

    db_comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not db_comment:
        logger.error("Comment not found", comment_id=comment_id)
        raise HTTPException(status_code=404, detail="Comment not found")

    if db_comment.user_id != current_user.id:
        logger.warning(
            "Unauthorized comment update attempt",
            comment_id=comment_id,
            user_id=current_user.id
        )
        raise HTTPException(status_code=403, detail="Not authorized to update this comment")

    db_comment.comment = comment_text
    db.commit()
    db.refresh(db_comment)

    logger.info("Comment updated successfully", comment_id=comment_id)
    return db_comment

@router.delete("/comments/{comment_id}", response_model=schemas.Comment, tags=["Comments"])
@trace_function("comment_deletion")
async def delete_comment(
        comment_id: int,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(get_db)
):
    """Delete a comment."""
    logger.info("Deleting comment", comment_id=comment_id, user_id=current_user.id)

    db_comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not db_comment:
        logger.error("Comment not found for deletion", comment_id=comment_id)
        raise HTTPException(status_code=404, detail="Comment not found")

    plant = db.query(models.Plant).filter(models.Plant.id == db_comment.plant_id).first()

    if db_comment.user_id != current_user.id and plant.owner_id != current_user.id:
        logger.warning(
            "Unauthorized comment deletion attempt",
            comment_id=comment_id,
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete this comment. Must be comment author or plant owner."
        )

    deleted_comment = schemas.Comment.model_validate(db_comment)
    db.delete(db_comment)
    db.commit()

    logger.info("Comment deleted successfully", comment_id=comment_id)
    return deleted_comment

@router.get("/users/{user_id}/comments/", response_model=list[schemas.Comment], tags=["Comments"])
@trace_function("get_user_comments")
async def get_user_comments(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.get_current_user)
):
    """Get all comments made by a specific user."""
    logger.info("Getting user comments", target_user_id=user_id, current_user_id=current_user.id)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger.error("User not found for comments", user_id=user_id)
        raise HTTPException(status_code=404, detail="User not found")

    comments = db.query(models.Comment).filter(models.Comment.user_id == user_id).all()

    logger.info("User comments retrieved", user_id=user_id, count=len(comments))
    return comments
