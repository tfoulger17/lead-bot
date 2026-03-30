from datetime import datetime, time
import os
import json
import requests
import smtplib
from email.mime.text import MIMEText

EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

MY_PHONE = "(602) 877-4288"
SEEN_FILE = "seen_leads.json"
pending_leads = []

import re

def choose_best_email(emails):
    if not emails:
        return None

    emails = list(set(email.lower() for email in emails))

    preferred_keywords = [
        "manager",
        "leasing",
        "regional",
        "operations",
        "property",
        "contact",
        "info",
    ]

    bad_keywords = [
        "support",
        "help",
        "careers",
        "jobs",
        "hiring",
        "privacy",
        "legal",
        "billing",
        "noreply",
        "no-reply",
    ]

    good_emails = []
    fallback_emails = []

    for email in emails:
        if any(bad in email for bad in bad_keywords):
            continue

        if any(pref in email for pref in preferred_keywords):
            good_emails.append(email)
        else:
            fallback_emails.append(email)

    if good_emails:
        return good_emails[0]

    if fallback_emails:
        return fallback_emails[0]

    return None

def extract_emails_from_website(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=10)
        html = response.text

        found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)

        emails = []
        for email in found:
            email = email.lower().strip()

            if any(x in email for x in [".png", ".jpg", ".jpeg", ".webp"]):
                continue

            emails.append(email)

        return list(set(emails))

    except Exception as e:
        print(f"Website email extraction error for {url}: {e}")
        return []

def send_email(to_email, subject, body):
    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
        "Content-Type": "application/json"
    }

    data = {
        "from": "Tony @ Elite EcoJunk <tony@elite-ecojunk.com>",
        "to": [to_email],
        "subject": subject,
        "html": f"<p>{body}</p>"
    }

    response = requests.post(url, json=data, headers=headers)

    print(response.text)

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

seen_leads = load_seen()
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM_PROMPT = """
You are Tony's AI operator.

Tony owns a junk removal company in Phoenix and wants practical help growing revenue.
Focus on:
- commercial junk removal
- property managers
- apartment contracts
- recurring revenue
- lead generation
- outreach
- operational improvements
- business development
- realistic online income ideas

Be direct, practical, and unbiased.
Do not give generic advice.
Challenge weak ideas and suggest better ones.
Prefer ideas with realistic ROI and fast implementation.
Do not claim to have completed actions you did not complete.
If asked to execute something, explain the plan first and ask for approval.
"""

pending_tasks = {}
found_leads = {}
import csv

def save_leads_to_csv(user_id, leads):
    filename = f"leads_{user_id}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Address", "Phone", "Website"])

        for lead in leads:
            writer.writerow([
                lead.get("name", ""),
                lead.get("address", ""),
                lead.get("phone", ""),
                lead.get("website", "")
            ])

    return filename

def search_places(query: str):
    api_key = os.environ["GOOGLE_PLACES_API_KEY"]
    url = "https://places.googleapis.com/v1/places:searchText"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.primaryType"
    }

    payload = {
        "textQuery": query,
        "maxResultCount": 50
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("places", [])


def get_place_details(place_id: str):
    api_key = os.environ["GOOGLE_PLACES_API_KEY"]
    url = f"https://places.googleapis.com/v1/places/{place_id}"

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,googleMapsUri,primaryType"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def save_leads_to_file(user_id: int, leads: list):
    filename = f"leads_{user_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2)
    return filename
def ask_model(user_text: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )
    return response.output_text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Tony AI Operator online")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    await update.message.reply_text(f"✅ System is running\nTime: {now}")

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    response = ask_model(prompt)
    await update.message.reply_text(response[:4000])

async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text("Use: /ideas <your question or goal>")
        return

    response = ask_model(f"Give me practical business ideas for: {prompt}")

    user_id = update.effective_user.id
    pending_tasks[user_id] = response

    await update.message.reply_text(response[:4000])
    await update.message.reply_text("Reply with /approve if you want to mark this as the approved direction.")

async def improve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    response = ask_model(f"How can I improve this: {prompt}")
    await update.message.reply_text(response[:4000])

def is_good_email(email):
    if not email:
        return False

    email = email.lower()

    bad = ["noreply", "support", "info", "help", "privacy", "legal"]
    good = ["manager", "leasing", "office", "admin", "team", "info"]

    if any(b in email for b in bad):
        return False

    if any(g in email for g in good):
        return True

    return False

async def leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args).strip()

    if not prompt:
        await update.message.reply_text("Use: /leads <target market and city>")
        return

    try:
        raw_places = search_places(prompt)

        if not raw_places:
            await update.message.reply_text("No leads found.")
            return

        new_leads = []

        for place in raw_places[:50]:
            place_id = place.get("id")
            if not place_id:
                continue

            details = get_place_details(place_id)

            name = details.get("displayName", {}).get("text", "Unknown").strip().lower()
            address = details.get("formattedAddress", "N/A").strip().lower()
            lead_key = f"{name}|{address}"

            if lead_key in seen_leads and len(new_leads) > 20:
                continue

            website = details.get("websiteUri", "N/A")

            emails_found = []
            best_email = None

            try:
                if website != "N/A":
                    emails_found = extract_emails_from_website(website)
                    best_email = choose_best_email(emails_found)
            except Exception as e:
                print(f"Email extraction failed: {e}")

            lead = {
                "name": details.get("displayName", {}).get("text", "Unknown"),
                "address": details.get("formattedAddress", "N/A"),
                "phone": details.get("nationalPhoneNumber", "N/A"),
                "website": website,
                "maps": details.get("googleMapsUri", "N/A"),
                "type": details.get("primaryType", "N/A"),
                "email": best_email if best_email else None,
            }

            if lead["email"] and is_good_email(lead["email"]):
                new_leads.append(lead)
                seen_leads.add(lead_key)

            if len(new_leads) >= 100:
                break

        save_seen(seen_leads)

        leads = new_leads

        if not leads:
            await update.message.reply_text(f"DEBUG: {len(new_leads)} leads after filtering")
            return

        user_id = update.effective_user.id
        pending_tasks[user_id] = {
            "type": "leads",
            "data": leads
        }

        filename = save_leads_to_csv(user_id, leads)

        with open(filename, "rb") as file:
            await update.message.reply_document(file)

        preview_lines = []
        for i, lead in enumerate(leads[:10], start=1):
            preview_lines.append(
                f"{i}. {lead['name']}\n"
                f"Address: {lead['address']}\n"
                f"Phone: {lead['phone']}\n"
                f"Website: {lead['website']}\n"
                f"Email: {lead['email']}"
            )

        preview = "\n\n".join(preview_lines)

        await update.message.reply_text(
            f"Found {len(leads)} NEW leads.\n\nShowing first 10 below:\n\n{preview[:3500]}"
        )

        await update.message.reply_text(
            f"Saved full results to {filename}\n"
            f"Reply /approve to approve these leads for the next step."
        )

    except Exception as e:
        await update.message.reply_text(f"Lead search error: {e}")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in pending_tasks:
        await update.message.reply_text("Nothing pending to approve.")
        return

    task = pending_tasks[user_id]
    leads = task["data"]

    await update.message.reply_text("✅ Approved. Sending test emails now...")

    sent_count = 0

    for lead in leads[:5]:
        name = lead.get("name", "there")
        address = lead.get("address", "")
        phone = lead.get("phone", "N/A")
        email = lead.get("email")

        if not email:
            continue

        subject = f"Quick question about {name}"

        body = f"""Hi {name} team,

This is Tony with Elite EcoJunk Removal. Hope you're doing well!

We help apartment communities and property management teams with bulk trash removal, cleanouts, and valet trash services throughout the Phoenix area.

I came across your property at:
{address}

A lot of the teams we work with needed help with:
• dumpster overflow and bulk item buildup
• faster unit turns after move-outs
• reducing extra strain on maintenance staff

I’d love to see if we could support your property or management team in a similar way.

Would you be open to a quick call this week?

Best,
Tony
Elite EcoJunk Removal
Phone: {MY_PHONE}
"""

        try:
            await update.message.reply_text(
                f"TO: {email}\n\nSUBJECT: {subject}\n\nBODY:\n{body}"
        )
            send_email(email, subject, body)
            sent_count += 1
        except Exception as e:
            print(f"Email failed for {name}: {e}")

    del pending_tasks[user_id]
    await update.message.reply_text(f"Done. Sent {sent_count} emails.")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_user.id))

async def auto_run(context: ContextTypes.DEFAULT_TYPE):
    chat_id = 6824705956

    prompts = [
        "apartment complexes phoenix az",
        "apartment communities scottsdale az",
        "apartment complexes tempe az",
        "apartment communities mesa az",
        "multifamily housing chandler az",
        "apartment complexes gilbert az",
        "property management phoenix az",
        "property management scottsdale az",
    ]

    try:
        new_leads = []

        for prompt in prompts:
            if len(new_leads) >= 100:
                break

            raw_places = search_places(prompt)

            if not raw_places:
                continue

            for place in raw_places[:50]:
                if len(new_leads) >= 100:
                    break

                place_id = place.get("id")
                if not place_id:
                    continue

                details = get_place_details(place_id)

                name = details.get("displayName", {}).get("text", "Unknown").strip().lower()
                address = details.get("formattedAddress", "N/A").strip().lower()
                lead_key = f"{name}|{address}"

                if lead_key in seen_leads:
                    continue

                lead = {
                    "name": details.get("displayName", {}).get("text", "Unknown"),
                    "address": details.get("formattedAddress", "N/A"),
                    "phone": details.get("nationalPhoneNumber", "N/A"),
                    "website": details.get("websiteUri", "N/A"),
                    "maps": details.get("googleMapsUri", "N/A"),
                    "type": details.get("primaryType", "N/A"),
                }

                new_leads.append(lead)
                seen_leads.add(lead_key)

            if len(new_leads) >= 100:
                break

        save_seen(seen_leads)

        if not new_leads:
            await context.bot.send_message(chat_id=chat_id, text="No NEW leads found today.")
            return

        pending_tasks[chat_id] = {
            "type": "leads",
            "data": new_leads
        }

        filename = save_leads_to_csv(chat_id, new_leads)

        with open(filename, "rb") as file:
            await context.bot.send_document(chat_id=chat_id, document=file)

        preview_lines = []
        for i, lead in enumerate(new_leads[:10], start=1):
            preview_lines.append(
                f"{i}. {lead['name']}\n"
                f"Address: {lead['address']}\n"
                f"Phone: {lead['phone']}\n"
                f"Website: {lead['website']}"
            )

        preview = "\n\n".join(preview_lines)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Found {len(new_leads)} NEW leads today.\n\nShowing first 10 below:\n\n{preview[:3500]}"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Saved full results to {filename}\nReply /approve to generate outreach."
        )

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Auto-run error: {e}")

async def run_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_run(context)

#send_email(
    #"tfoulger17@gmail.com",
    #"Test Email",
    #"Your bot is working 🚀"
#)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("ask", ask))
app.add_handler(CommandHandler("improve", improve))
app.add_handler(CommandHandler("approve", approve))
app.add_handler(CommandHandler("leads", leads))
app.add_handler(CommandHandler("id", get_id))
app.add_handler(CommandHandler("runnow", run_now))

#app.job_queue.run_daily(auto_run, time=time(hour=20, minute=22))

app.run_polling()
