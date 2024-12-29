from .database import Base
from sqlalchemy import Column, Integer, String, Date, JSON, Text, DateTime, func
from sqlalchemy import event
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

class LinkedInAd(Base):
    __tablename__ = "linkedin_ads"
    __table_args__ = {'schema': 'public'}

    ad_id = Column(String(50), primary_key=True)
    creative_type = Column(String(100))
    advertiser_name = Column(String(255))
    advertiser_logo = Column(Text)
    headline = Column(Text)
    description = Column(Text)
    promoted_text = Column(Text)
    image_url = Column(Text)
    view_details_link = Column(Text)
    campaign_start_date = Column(Date)
    campaign_end_date = Column(Date)
    campaign_impressions_range = Column(String(100))
    campaign_impressions_by_country = Column(JSON)
    company_id = Column(Integer, nullable=False)
    ad_type = Column(String(50))
    ad_redirect_url = Column(Text)
    utm_parameters = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
  
@event.listens_for(Session, 'after_flush')
def receive_after_flush(session, flush_context):
    logger.info(f"Flushed: Additions={len(session.new)}, "
                f"Modifications={len(session.dirty)}, "
                f"Deletions={len(session.deleted)}")
  