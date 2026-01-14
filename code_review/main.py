"""Local CLI for testing AI Code Review."""

import argparse
import asyncio
import os
import sys

from .config import CodeReviewConfig
from .context_builder import ContextBuilder
from .formatter import ReviewFormatter
from .pr_fetcher import PRFetcher, PRSizeError
from .reviewer import AIReviewer


async def main():
    """Local testing CLI."""
    parser = argparse.ArgumentParser(description="AI Code Review - Local Testing")
    parser.add_argument("--pr", type=int, required=True, help="PR number to review")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument(
        "--no-post", action="store_true", help="Don't post review (just print)"
    )
    args = parser.parse_args()

    # Set environment variables for testing
    os.environ["GITHUB_REPO"] = args.repo
    os.environ.setdefault("PROJECT_ROOT", os.getcwd())

    # Validate required env vars
    if not os.getenv("GITHUB_TOKEN"):
        print("Error: GITHUB_TOKEN environment variable required")
        return 1

    if not os.getenv("GIGACHAT_CREDENTIALS"):
        print("Error: GIGACHAT_CREDENTIALS environment variable required")
        return 1

    try:
        # Load configuration
        config = CodeReviewConfig.from_env()
        print(f"Repository: {config.github_repo}")
        print(f"PR Number: {args.pr}")
        print(f"Project Root: {config.project_root}\n")

        # Initialize components
        pr_fetcher = PRFetcher(config)
        context_builder = ContextBuilder(config)
        reviewer = AIReviewer(config)
        formatter = ReviewFormatter()

        try:
            # Fetch PR
            print("Fetching PR details...")
            pr_data = await pr_fetcher.fetch_pr_details(args.pr)
            print(f"Title: {pr_data.title}")
            print(f"Author: {pr_data.author}")
            print(f"Files: {pr_data.files_changed}, Lines: +{pr_data.lines_added} -{pr_data.lines_deleted}\n")

            # Validate size
            try:
                pr_fetcher.validate_pr_size(pr_data)
            except PRSizeError as e:
                print(f"Warning: {e}")
                response = input("Continue anyway? (y/n): ")
                if response.lower() != "y":
                    return 0

            # Fetch files
            print("Fetching PR files...")
            pr_files = await pr_fetcher.fetch_pr_files(args.pr)
            print(f"Fetched {len(pr_files)} files\n")

            # Build context
            print("Building context with RAG...")
            try:
                context = await context_builder.build_context(pr_data, pr_files)
                print(f"Context: ~{context.token_count} tokens\n")
            except Exception as e:
                print(f"Warning: RAG failed ({e}), using minimal context\n")
                context = await context_builder.build_minimal_context(pr_data, pr_files)

            # Generate review
            print("Generating review with GigaChat...")
            review_result = await reviewer.review_pr(context)
            print(
                f"Review complete: {len(review_result.blocking_issues)} blocking, "
                f"{len(review_result.non_blocking_issues)} non-blocking\n"
            )

            # Format review
            review_markdown = formatter.format_review(review_result, pr_data.html_url)

            # Print review
            print("=" * 80)
            print(review_markdown)
            print("=" * 80)

            # Post if requested
            if not args.no_post:
                from .poster import ReviewPoster

                poster = ReviewPoster(config)
                try:
                    print("\nPosting review to GitHub...")
                    await poster.post_review(args.pr, review_markdown)
                    print("✓ Review posted successfully!")
                finally:
                    await poster.close()
            else:
                print("\n(Review not posted - use without --no-post to post)")

            return 0

        finally:
            await pr_fetcher.close()

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
