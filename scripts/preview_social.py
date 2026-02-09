#!/usr/bin/env python3
"""Preview social media adaptations for all platforms + push Slack to Postiz.

Usage:
    set -a && source .env && set +a
    uv run python scripts/preview_social.py insights/blog/weekly/weekly-2026-W06.md
"""

import sys
from pathlib import Path

# Strip frontmatter from blog post
def extract_prose(filepath: str) -> str:
    text = Path(filepath).read_text()
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()
    return text


def main():
    if len(sys.argv) < 2:
        print("Usage: preview_social.py <blog-post.md>")
        sys.exit(1)

    prose = extract_prose(sys.argv[1])
    slug = Path(sys.argv[1]).stem

    from distill.blog.config import BlogConfig
    from distill.blog.prompts import SOCIAL_PROMPTS
    from distill.blog.synthesizer import BlogSynthesizer

    config = BlogConfig(target_word_count=1200)
    synth = BlogSynthesizer(config)

    platforms = list(SOCIAL_PROMPTS.keys())
    print(f"Adapting for {len(platforms)} platforms: {', '.join(platforms)}\n")

    output_dir = Path("insights/blog/social-preview")
    output_dir.mkdir(parents=True, exist_ok=True)

    for platform in platforms:
        print(f"{'='*60}")
        print(f"  Adapting for: {platform.upper()}")
        print(f"{'='*60}")
        try:
            adapted = synth.adapt_for_platform(prose, platform, slug)
            outfile = output_dir / f"{slug}-{platform}.md"
            outfile.write_text(adapted)
            print(adapted)
            print(f"\n  -> Saved to {outfile}\n")
        except Exception as e:
            print(f"  ERROR: {e}\n")

    # Push Slack version to Postiz as scheduled
    print(f"\n{'='*60}")
    print("  Pushing Slack version to Postiz...")
    print(f"{'='*60}")
    try:
        from distill.integrations.postiz import PostizClient, PostizConfig
        from distill.integrations.scheduling import next_weekly_slot

        pconfig = PostizConfig.from_env()
        if not pconfig.is_configured:
            print("  Postiz not configured, skipping push")
            return

        client = PostizClient(pconfig)
        integrations = client.list_integrations()
        slack_ids = [i.id for i in integrations if i.provider == "slack"]

        if not slack_ids:
            print("  No Slack integration found in Postiz")
            return

        slack_content = (output_dir / f"{slug}-slack.md").read_text()
        post_type = pconfig.resolve_post_type()
        scheduled_at = None
        if post_type == "schedule":
            scheduled_at = next_weekly_slot(pconfig)

        result = client.create_post(
            slack_content,
            slack_ids,
            post_type=post_type,
            scheduled_at=scheduled_at,
        )
        if scheduled_at:
            print(f"  Scheduled for {scheduled_at}")
        else:
            print(f"  Draft created")
        print(f"  API response: {result}")
    except Exception as e:
        print(f"  ERROR pushing to Postiz: {e}")


if __name__ == "__main__":
    main()
