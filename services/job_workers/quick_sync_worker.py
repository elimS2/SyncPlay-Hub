#!/usr/bin/env python3
"""
Quick Sync Worker

Worker for executing quick sync jobs in the job queue system.
"""

import os
import sys
import time
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.job_types import JobType, JobWorker, Job
from services.channel_sync_service import ChannelSyncService
from controllers.api.shared import log_message


class QuickSyncWorker(JobWorker):
    """Worker for executing quick sync jobs."""
    
    def __init__(self, worker_id: str = "quick_sync_worker"):
        super().__init__(worker_id)
        self.sync_service = ChannelSyncService()
    
    def get_supported_job_types(self) -> List[JobType]:
        """Returns list of supported job types."""
        return [JobType.QUICK_SYNC]
    
    def execute_job(self, job: Job) -> bool:
        """
        Executes quick sync job.
        
        Args:
            job: Job to execute
            
        Returns:
            True if job executed successfully, False if failed
        """
        try:
            # Extract job data
            channel_id = job.job_data.get('channel_id')
            
            if not channel_id:
                job.log_error("No channel_id provided in job data")
                return False
            
            job.log_info(f"Starting quick sync for channel ID: {channel_id}")
            
            # Execute quick sync using the service
            result = self.sync_service.quick_sync_channel_core(channel_id)
            
            # Log the result
            if result.get('status') == 'started':
                job.log_info(f"Quick sync started successfully: {result.get('new_videos', 0)} new videos found")
                job.log_info(f"Download jobs created: {result.get('jobs_created', 0)}")
                job.log_info(f"Batches processed: {result.get('batches_processed', 0)}")
                return True
            elif result.get('status') == 'up_to_date':
                job.log_info("Channel is up to date, no new videos to download")
                return True
            elif result.get('status') == 'no_metadata':
                job.log_error("No metadata found for channel, full sync needed first")
                return False
            else:
                job.log_error(f"Quick sync failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            job.log_exception(e, "execute_job in QuickSyncWorker")
            return False


def main():
    """Test the worker."""
    worker = QuickSyncWorker()
    print(f"Worker {worker.worker_id} supports: {[jt.value for jt in worker.get_supported_job_types()]}")


if __name__ == "__main__":
    main() 