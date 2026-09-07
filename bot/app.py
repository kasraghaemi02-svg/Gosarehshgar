from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time

import holidays
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import load_config
from .db import init_db, get_all_cases, update_case_status, get_interviews, update_interview_reminder, get_users_by_role
from .handlers import router as main_router
from .handlers_start import router as start_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_work_day() -> bool:
    now = datetime.now()
    de_holidays = holidays.CountryHoliday('DE', years=now.year)
    if now.weekday() >= 5:
        return False
    if now.date() in de_holidays:
        return False
    return True


def is_work_hour() -> bool:
    now = datetime.now()
    work_start = time(9, 0)
    work_end = time(19, 0)
    return work_start <= now.time() < work_end


async def send_event_payment_reminder(bot: Bot, db_path: str, reminder: dict):
    case = db.get_case(db_path, reminder["case_id"])
    if not case: return
    
    installments = db.get_installments(db_path, reminder["case_id"])
    inst = next((i for i in installments if i["id"] == reminder["installment_id"]), None)
    if not inst or inst["is_paid"]:
        db.update_reminder_status(db_path, reminder["id"], reminder["sent_count"], is_completed=1)
        return

    reminder_names = {
        "initial": "عقد قرارداد",
        "interview": "مصاحبه",
        "contract": "قرارداد کارفرما",
        "pre_approval": "پیش‌تاییدیه"
    }
    event_name = reminder_names.get(reminder["reminder_type"], "مرحله جدید")
    
    # Text for User (Client/Agency/Blogger)
    if reminder["reminder_type"] == "initial":
        user_text = (
            f"🌸 *یادآوری صمیمانه پرداخت قسط اول*\n\n"
            f"کاربر گرامی، ضمن عرض تبریک بابت عقد قرارداد برای پرونده «{case['client_name']}»، "
            f"به استحضار می‌رساند که طبق توافقات، قسط اول می‌بایست همزمان با عقد قرارداد پرداخت می‌گردید.\n\n"
            f"چنانچه تاکنون موفق به واریز نشده‌اید، محبت فرموده در اسرع وقت نسبت به تسویه این قسط اقدام نمایید تا روند پرونده بدون وقفه ادامه یابد. 🙏\n\n"
            f"💰 مبلغ قسط: {format_amount(inst['amount'])}\n"
            f"📌 وضعیت: در انتظار واریز"
        )
    else:
        user_text = (
            f"✨ *اطلاعیه واریز وجه*\n\n"
            f"کاربر گرامی، با توجه به انجام مرحله «*{event_name}*» برای پرونده «{case['client_name']}»، "
            f"طبق قرارداد فیمابین، لطفاً نسبت به واریز قسط مربوطه اقدام فرمایید.\n\n"
            f"💰 مبلغ قسط: {format_amount(inst['amount'])}\n"
            f"📋 شماره قسط: {inst['idx']}\n\n"
            f"🙏 ممنون از همکاری شما."
        )
    
    # Text for Admin
    if reminder["reminder_type"] == "initial":
        admin_text = (
            f"🚨 *عدم پرداخت قسط اول (عقد قرارداد)*\n\n"
            f"پرونده `{case['case_id']}` ({case['client_name']}) عقد قرارداد شده است، "
            f"اما قسط اول به مبلغ {format_amount(inst['amount'])} هنوز پرداخت نشده است."
        )
    else:
        admin_text = (
            f"⚠️ *یادآوری عدم پرداخت قسط*\n\n"
            f"مرحله «*{event_name}*» برای پرونده `{case['case_id']}` انجام شده است، "
            f"اما قسط شماره {inst['idx']} به مبلغ {format_amount(inst['amount'])} هنوز پرداخت نشده است."
        )

    from .keyboards import kb_admin_payment_notification, kb_client_payment_notification
    
    # Send to User (License Owner)
    lic_users = db.get_users_by_license(db_path, case["owner_license_code"])
    for u in lic_users:
        try:
            await bot.send_message(u["user_id"], user_text, parse_mode="Markdown", reply_markup=kb_client_payment_notification(case["case_id"]))
        except: pass

    # Send to Admins
    admins = db.get_all_admin_users(db_path)
    for a in admins:
        try:
            await bot.send_message(a["user_id"], admin_text, parse_mode="Markdown", reply_markup=kb_admin_payment_notification(case["case_id"], inst["id"], reminder["id"]))
        except: pass

    # Update reminder status
    new_count = reminder["sent_count"] + 1
    # Stop after 2 reminders for ALL installment types as requested
    is_done = 1 if new_count >= 2 else 0
    db.update_reminder_status(db_path, reminder["id"], new_count, is_completed=is_done)


async def check_admin_24h_interview_reminders(bot: Bot, db_path: str):
    """Sends a reminder to super admin 24 hours before any interview."""
    try:
        from datetime import datetime, timedelta
        now = datetime.now()
        # Look for interviews in the next 24-25 hours
        start_time = (now + timedelta(hours=23, minutes=45)).isoformat(timespec="seconds")
        end_time = (now + timedelta(hours=24, minutes=15)).isoformat(timespec="seconds")
        
        with db.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM interviews WHERE scheduled_at_iso >= ? AND scheduled_at_iso <= ? AND admin_24h_sent = 0",
                (start_time, end_time)
            ).fetchall()
            interviews = [dict(r) for r in rows]

        if not interviews:
            return

        cfg = load_config()
        super_admin_id = cfg.super_admin_id

        for iv in interviews:
            case = db.get_case(db_path, iv["case_id"])
            client_name = case["client_name"] if case else "نامشخص"
            
            dt = datetime.fromisoformat(iv["scheduled_at_iso"].replace('Z', '+00:00'))
            time_str = dt.strftime("%H:%M")
            date_str = dt.strftime("%Y/%m/%d")

            text = (
                f"🔔 *یادآوری ۲۴ ساعت تا مصاحبه*\n\n"
                f"👤 متقاضی: {client_name}\n"
                f"🏢 شرکت: {iv.get('company_name') or 'نامشخص'}\n"
                f"📅 تاریخ: `{date_str}`\n"
                f"⏰ ساعت: `{time_str}`\n"
                f"📂 پرونده: `{iv['case_id']}`\n\n"
                f"این مصاحبه تا ۲۴ ساعت آینده برگزار خواهد شد."
            )
            
            try:
                await bot.send_message(super_admin_id, text, parse_mode="Markdown")
                with db.connect(db_path) as conn:
                    conn.execute("UPDATE interviews SET admin_24h_sent = 1 WHERE id = ?", (iv["id"],))
            except Exception as e:
                logger.error(f"Failed to send admin 24h reminder for iv {iv['id']}: {e}")

    except Exception as e:
        logger.error(f"Error in check_admin_24h_interview_reminders: {e}")


async def check_pending_payment_reminders(bot: Bot, db_path: str):
    try:
        reminders = db.get_pending_reminders(db_path)
        now = datetime.now()
        for r in reminders:
            sent_count = r["sent_count"]
            
            if sent_count == 0:
                # 1st reminder: wait 1 day after creation
                created_at = datetime.fromisoformat(r["created_at"])
                if (now - created_at).total_seconds() < 24 * 3600 - 3600: # 1 day minus 1h buffer
                    continue
            elif sent_count == 1:
                # 2nd reminder: wait 3 days after the 1st reminder
                if not r["last_sent_at"]: continue
                last_sent = datetime.fromisoformat(r["last_sent_at"])
                if (now - last_sent).total_seconds() < 3 * 24 * 3600 - 3600: # 3 days minus 1h buffer
                    continue
            else:
                # Already sent 2 times or more, should have been marked as completed
                continue
                
            await send_event_payment_reminder(bot, db_path, r)
    except Exception as e:
        logger.error(f"Error in check_pending_payment_reminders: {e}")

async def check_work_hours(bot: Bot, db_path: str):
    try:
        in_work = is_work_hour()
        is_work = is_work_day()
        cases = get_all_cases(db_path)
        for case in cases:
            if not case.get("is_active"):
                continue
        if is_work:
            if not in_work:
                if case["status"] != "yellow":
                    update_case_status(db_path, case["case_id"], "yellow", "خارج از تایم کاری")
            elif in_work:
                if case["status"] == "yellow" and case.get("yellow_reason") == "خارج از تایم کاری":
                    if case.get("prev_status"):
                        update_case_status(db_path, case["case_id"], case["prev_status"])
        else:
            if case["status"] != "yellow":
                update_case_status(db_path, case["case_id"], "yellow", "خارج از تایم کاری")

    except Exception as e:
        logger.error(f"Error in check_work_hours: {e}")


async def check_interview_reminders(bot: Bot, db_path: str):
    try:
        now = datetime.now()
        interviews = get_interviews(db_path)
        for iv in interviews:
            if iv.get("status") in ("cancelled", "completed", "no_show"):
                continue
            if not iv.get("scheduled_at_iso"):
                continue
            try:
                iv_time = datetime.fromisoformat(iv["scheduled_at_iso"])
            except:
                continue
            diff = (iv_time - now).total_seconds() / 3600
            user = db.get_user(db_path, iv.get("created_by_user_id", 0))
            if not user:
                continue
                
            # Telegram Reminders
            if 23 <= diff <= 24 and not iv.get("reminder_24h_sent"):
                await bot.send_message(user["user_id"], f"⏰ یادآوری: مصاحبه {iv['company_name']} فردا است!")
                update_interview_reminder(db_path, iv["id"], "24h")
            elif 11 <= diff <= 12 and not iv.get("reminder_12h_sent"):
                await bot.send_message(user["user_id"], f"⏰ یادآوری: مصاحبه {iv['company_name']} تا 12 ساعت دیگر!")
                update_interview_reminder(db_path, iv["id"], "12h")
            elif 0.5 <= diff <= 1 and not iv.get("reminder_1h_sent"):
                await bot.send_message(user["user_id"], f"⏰ یادآوری: مصاحبه {iv['company_name']} تا 1 ساعت دیگر!")
                update_interview_reminder(db_path, iv["id"], "1h")

            # SMS Reminders (Newly added)
            from .sms_service import sms_service
            if 23 <= diff <= 24.5 and not iv.get("sms_sent_24h"):
                await sms_service.send_interview_reminder(db_path, iv["id"], "24h")
            elif 1.5 <= diff <= 2.5 and not iv.get("sms_sent_2h"):
                await sms_service.send_interview_reminder(db_path, iv["id"], "2h")
    except Exception as e:
        logger.error(f"Error in check_interview_reminders: {e}")


async def check_interview_followups(bot: Bot, db_path: str, cfg):
    try:
        now = datetime.now()
        interviews = get_interviews(db_path)
        for iv in interviews:
            if iv.get("status") in ("cancelled", "completed", "no_show"):
                continue
            if not iv.get("scheduled_at_iso"):
                continue
            if iv.get("followup_result"):
                continue
            try:
                iv_time = datetime.fromisoformat(iv["scheduled_at_iso"])
            except:
                continue
            diff = (now - iv_time).total_seconds() / 60
            if diff < 30:
                continue
            if iv.get("followup_30m_sent"):
                if iv.get("followup_count", 0) >= 3:
                    continue
                if iv.get("followup_result") == "in_progress":
                    pass
                else:
                    continue
            case = db.get_case(db_path, iv["case_id"])
            if not case:
                continue
            user = db.get_user(db_path, case.get("owner_license_code"))
            if not user:
                continue
            followup_count = iv.get("followup_count", 0) + 1
            if iv.get("followup_result") == "in_progress":
                text = f"🕐 وضعیت مصاحبه {iv['company_name']}؟\n\nدر حال انجام / انجام شد"
                buttons = [
                    [InlineKeyboardButton(text="🔄 در حال انجام", callback_data=f"iv_follow_{iv['id']}_in_progress")],
                    [InlineKeyboardButton(text="✅ انجام شد", callback_data=f"iv_follow_{iv['id']}_completed")],
                ]
            else:
                text = f"⏰ ۳۰ دقیقه از مصاحبه {iv['company_name']} گذشت\n\nوضعیت مصاحبه چی بود؟"
                buttons = [
                    [InlineKeyboardButton(text="✅ انجام شد", callback_data=f"iv_follow_{iv['id']}_completed")],
                    [InlineKeyboardButton(text="🔄 در حال انجام", callback_data=f"iv_follow_{iv['id']}_in_progress")],
                    [InlineKeyboardButton(text="❌ انجام نشد", callback_data=f"iv_follow_{iv['id']}_no_show")],
                ]
            await bot.send_message(user["user_id"], text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
            with db.connect(db_path) as conn:
                conn.execute("UPDATE interviews SET followup_30m_sent = 1, followup_count = ? WHERE id = ?", (followup_count, iv["id"]))
    except Exception as e:
        logger.error(f"Error in check_interview_followups: {e}")


def update_fake_counters(db_path: str):
    import random
    from datetime import datetime
    now = datetime.now()
    if now.weekday() == 4:
        return
    cases = db.get_all_cases(db_path)
    for case in cases:
        if case.get("status") == "archived":
            continue
        in_req = case.get("in_requests_count", 0)
        pres = case.get("presentations_count", 0)
        new_in_req = in_req + random.randint(20, 50)
        new_pres = pres + random.randint(1, 2)
        db.update_case_counters(db_path, case["case_id"], new_in_req, new_pres)


async def async_main() -> None:
    cfg = load_config()
    init_db(cfg.db_path)

    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp["scheduler"] = AsyncIOScheduler(timezone=cfg.timezone)
    scheduler = dp["scheduler"]
    dp["cfg"] = cfg
    dp["db_path"] = cfg.db_path

    dp.include_router(start_router)
    dp.include_router(main_router)

    scheduler.add_job(check_work_hours, "interval", minutes=30, args=[bot, cfg.db_path])
    scheduler.add_job(check_pending_payment_reminders, "interval", minutes=60, args=[bot, cfg.db_path])
    scheduler.add_job(check_admin_24h_interview_reminders, "interval", minutes=15, args=[bot, cfg.db_path])
    scheduler.add_job(check_interview_reminders, "interval", minutes=15, args=[bot, cfg.db_path])
    scheduler.add_job(check_interview_followups, "interval", minutes=10, args=[bot, cfg.db_path, cfg])
    scheduler.add_job(lambda: update_fake_counters(cfg.db_path), "cron", hour=9, minute=0)
    scheduler.start()

    await dp.start_polling(bot, cfg=cfg, db_path=cfg.db_path, scheduler=scheduler)


def main() -> None:
    asyncio.run(async_main())
