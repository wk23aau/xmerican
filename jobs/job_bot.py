"""
Job Application Bot - Automated job searching and application
Uses xCLICK for browser automation
"""

import asyncio
import sys
sys.path.insert(0, '../xCLICK')

from xclick import xClick

# Credentials from file
CREDENTIALS = {
    "name": "Waseem Raza Khan",
    "email": "waseemrazakhansqa@gmail.com",
    "phone": "+447404132345",
    "linkedin": "https://www.linkedin.com/in/khanwaseemraza/",
    "location": "London, UK",
}

# CV content for filling forms
CV_SUMMARY = """QA Engineer with specialized expertise in AI/LLM testing and data validation. 
Experienced in Python, TypeScript, and Playwright automation with strong Docker, Kubernetes, 
and CI/CD pipeline knowledge. Currently completing MSc Data Science focusing on NLP and 
transformer models."""


class JobBot:
    def __init__(self):
        self.xclick = xClick()
        self.jobs_applied = []
        
    async def connect(self):
        await self.xclick.connect()
        
    async def goto_testdevjobs(self):
        """Navigate to TestDevJobs"""
        await self.xclick.goto("https://testdevjobs.com")
        await asyncio.sleep(2)
        
    async def scroll_down(self, amount: int = 500):
        """Scroll down the page"""
        await self.xclick.cdp.send("Runtime.evaluate", {
            "expression": f"window.scrollBy(0, {amount})"
        })
        await asyncio.sleep(0.5)
        
    async def scroll_up(self, amount: int = 500):
        """Scroll up the page"""
        await self.xclick.cdp.send("Runtime.evaluate", {
            "expression": f"window.scrollBy(0, -{amount})"
        })
        await asyncio.sleep(0.5)
        
    async def get_job_links(self) -> list:
        """Get all job links on current page"""
        await self.xclick.refresh_probes()
        jobs = []
        for probe in self.xclick.probes:
            text = probe.get("text", "").lower()
            ptype = probe.get("type", "")
            # Look for job titles (usually contains job-related keywords)
            if ptype == "link" and any(kw in text for kw in ["engineer", "qa", "test", "automation", "developer"]):
                jobs.append(probe)
        return jobs
        
    async def find_apply_button(self) -> dict:
        """Find the Apply button on a job page"""
        await self.xclick.refresh_probes()
        for probe in self.xclick.probes:
            text = probe.get("text", "").lower()
            if "apply" in text and probe.get("type") in ("button", "link"):
                return probe
        return None
        
    async def fill_application_form(self):
        """Fill out job application form"""
        await self.xclick.refresh_probes()
        
        for probe in self.xclick.probes:
            text = probe.get("text", "").lower()
            ptype = probe.get("type", "")
            
            if ptype != "input":
                continue
                
            cx, cy = probe.get("cx", 0), probe.get("cy", 0)
            
            # Match field to credential
            if any(kw in text for kw in ["name", "full name"]):
                await self.xclick.cdp.mouse_click(cx, cy)
                await asyncio.sleep(0.3)
                await self.xclick.type_text(CREDENTIALS["name"])
                
            elif any(kw in text for kw in ["email", "e-mail"]):
                await self.xclick.cdp.mouse_click(cx, cy)
                await asyncio.sleep(0.3)
                await self.xclick.type_text(CREDENTIALS["email"])
                
            elif any(kw in text for kw in ["phone", "mobile", "tel"]):
                await self.xclick.cdp.mouse_click(cx, cy)
                await asyncio.sleep(0.3)
                await self.xclick.type_text(CREDENTIALS["phone"])
                
            elif "linkedin" in text:
                await self.xclick.cdp.mouse_click(cx, cy)
                await asyncio.sleep(0.3)
                await self.xclick.type_text(CREDENTIALS["linkedin"])
                
            elif any(kw in text for kw in ["location", "city"]):
                await self.xclick.cdp.mouse_click(cx, cy)
                await asyncio.sleep(0.3)
                await self.xclick.type_text(CREDENTIALS["location"])
                
            elif any(kw in text for kw in ["summary", "about", "cover"]):
                await self.xclick.cdp.mouse_click(cx, cy)
                await asyncio.sleep(0.3)
                await self.xclick.type_text(CV_SUMMARY)
                
    async def click_submit(self):
        """Click submit button"""
        await self.xclick.refresh_probes()
        for probe in self.xclick.probes:
            text = probe.get("text", "").lower()
            if any(kw in text for kw in ["submit", "send", "apply"]):
                if probe.get("type") in ("button", "link"):
                    cx, cy = probe.get("cx", 0), probe.get("cy", 0)
                    await self.xclick.cdp.mouse_click(cx, cy)
                    print(f"✓ Submitted application")
                    return True
        return False
        
    async def apply_to_job(self, job_probe: dict):
        """Full flow to apply to a single job"""
        job_title = job_probe.get("text", "Unknown")[:50]
        print(f"\n📋 Applying to: {job_title}")
        
        # Click on job
        cx, cy = job_probe.get("cx", 0), job_probe.get("cy", 0)
        await self.xclick.cdp.mouse_click(cx, cy)
        await asyncio.sleep(3)
        
        # Find and click Apply button
        apply_btn = await self.find_apply_button()
        if apply_btn:
            await self.xclick.cdp.mouse_click(apply_btn["cx"], apply_btn["cy"])
            await asyncio.sleep(2)
            
            # Fill form
            await self.fill_application_form()
            await asyncio.sleep(1)
            
            # Submit
            if await self.click_submit():
                self.jobs_applied.append(job_title)
                return True
        else:
            print(f"  ⚠ No Apply button found")
            
        return False
        
    async def run(self, max_jobs: int = 5):
        """Main bot loop"""
        print("🤖 Job Application Bot Starting...")
        await self.connect()
        
        # Go to testdevjobs
        await self.goto_testdevjobs()
        
        jobs_processed = 0
        page = 1
        
        while jobs_processed < max_jobs:
            print(f"\n📄 Page {page}")
            
            # Get jobs on this page
            jobs = await self.get_job_links()
            print(f"  Found {len(jobs)} job listings")
            
            for job in jobs[:max_jobs - jobs_processed]:
                await self.apply_to_job(job)
                jobs_processed += 1
                
                # Go back to listings
                await self.xclick.cdp.send("Runtime.evaluate", {
                    "expression": "window.history.back()"
                })
                await asyncio.sleep(2)
                
            # Check for next page
            await self.xclick.refresh_probes()
            next_btn = None
            for probe in self.xclick.probes:
                if "next" in probe.get("text", "").lower():
                    next_btn = probe
                    break
                    
            if next_btn:
                await self.xclick.cdp.mouse_click(next_btn["cx"], next_btn["cy"])
                await asyncio.sleep(2)
                page += 1
            else:
                print("  No more pages")
                break
                
        print(f"\n✅ Applied to {len(self.jobs_applied)} jobs:")
        for job in self.jobs_applied:
            print(f"  • {job}")
            
        await self.xclick.close()


async def main():
    bot = JobBot()
    await bot.run(max_jobs=3)


if __name__ == "__main__":
    asyncio.run(main())
