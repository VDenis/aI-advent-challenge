"""GitHub Actions entry point for AI Code Review."""

import asyncio
import logging
import os
import sys

from .config import CodeReviewConfig
from .context_builder import ContextBuilder
from .formatter import ReviewFormatter
from .poster import ReviewPoster
from .pr_fetcher import PRFetcher, PRSizeError
from .reviewer import AIReviewer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


async def main() -> int:
    """Main orchestrator for GitHub Actions."""
    try:
        # Read environment variables
        pr_number = os.getenv("PR_NUMBER")
        if not pr_number:
            logger.error("PR_NUMBER environment variable not set")
            return 1

        try:
            pr_number = int(pr_number)
        except ValueError:
            logger.error(f"Invalid PR_NUMBER: {pr_number}")
            return 1

        logger.info(f"Starting AI code review for PR #{pr_number}")

        # Load configuration
        try:
            config = CodeReviewConfig.from_env()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            return 1

        logger.info(f"Repository: {config.github_repo}")
        logger.info(f"Project root: {config.project_root}")

        # Initialize components
        pr_fetcher = PRFetcher(config)
        context_builder = ContextBuilder(config)
        reviewer = AIReviewer(config)
        formatter = ReviewFormatter()
        poster = ReviewPoster(config)

        try:
            # Step 1: Fetch PR data
            logger.info("Fetching PR details...")
            pr_data = await pr_fetcher.fetch_pr_details(pr_number)
            logger.info(
                f"PR: {pr_data.title} by {pr_data.author} "
                f"({pr_data.files_changed} files, +{pr_data.lines_added} -{pr_data.lines_deleted})"
            )

            # Step 2: Validate PR size
            try:
                pr_fetcher.validate_pr_size(pr_data)
            except PRSizeError as e:
                logger.warning(f"PR size exceeds limits: {e}")
                total_lines = pr_data.lines_added + pr_data.lines_deleted
                await poster.post_size_warning(pr_number, pr_data.files_changed, total_lines)
                return 0  # Not a failure, just skipped

            # Step 3: Fetch PR files
            logger.info("Fetching PR files...")
            pr_files = await pr_fetcher.fetch_pr_files(pr_number)
            logger.info(f"Fetched {len(pr_files)} changed files")

            # Step 4: Build context with RAG
            logger.info("Building review context with RAG...")
            try:
                context = await context_builder.build_context(pr_data, pr_files)
                logger.info(f"Context built: ~{context.token_count} tokens")
            except Exception as e:
                logger.warning(f"RAG context building failed: {e}, using minimal context")
                context = await context_builder.build_minimal_context(pr_data, pr_files)

            # Step 5: Generate review
            logger.info("Generating AI review with GigaChat...")
            review_result = await reviewer.review_pr(context)
            logger.info(
                f"Review generated: {len(review_result.blocking_issues)} blocking, "
                f"{len(review_result.non_blocking_issues)} non-blocking issues"
            )

            # Step 6: Format review
            logger.info("Formatting review as Markdown...")
            review_markdown = formatter.format_review(review_result, pr_data.html_url)

            # Step 7: Post review
            logger.info("Posting review to GitHub...")
            await poster.post_review(pr_number, review_markdown)
            logger.info("Review posted successfully!")

            return 0

        finally:
            # Cleanup
            await pr_fetcher.close()
            await poster.close()

    except Exception as e:
        logger.exception(f"Unexpected error during code review: {e}")

        # Try to post error comment
        try:
            if "pr_number" in locals() and "poster" in locals():
                await poster.post_error_comment(pr_number, str(e))
        except Exception as post_error:
            logger.error(f"Failed to post error comment: {post_error}")

        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
