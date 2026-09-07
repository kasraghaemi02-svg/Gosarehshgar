"""SMS service using Melipayamak API with session management"""

import logging
import re
from datetime import datetime
from typing import Optional, Tuple

from .config import load_config
cfg = load_config()

logger = logging.getLogger(__name__)

# Import session manager
try:
    from .melipayamak_session import setup_melipayamak_session, clear_melipayamak_session
    SESSION_MANAGER_AVAILABLE = True
except ImportError:
    SESSION_MANAGER_AVAILABLE = False
    logger.warning("Session manager not available, using direct login")


class SMSService:
    """Service for sending SMS via Melipayamak API"""

    def __init__(self):
        self.username = cfg.melipayamak_username
        self.password = cfg.melipayamak_password
        self.api_url = cfg.melipayamak_api_url
        self.sms_templates = cfg.sms_templates
        self.client = None
        # Don't initialize in __init__ to avoid blocking or errors during startup if no 2FA

    def _initialize_client(self, code=None):
        """Initialize SOAP client with session management"""
        try:
            # Enable session manager for 2FA support
            if SESSION_MANAGER_AVAILABLE:
                # Try to use session manager
                success, result = setup_melipayamak_session(
                    self.username, self.password, code=code
                )
                if success:
                    self.client = result
                    logger.info("Melipayamak SMS client initialized with session")
                else:
                    logger.error(f"Session login failed: {result}")
                    self.client = None
                    return success, result
            else:
                # Fallback to direct initialization
                from zeep import Client
                from zeep.transports import Transport
                from requests import Session

                session = Session()
                session.timeout = 30
                transport = Transport(session=session)

                self.client = Client(self.api_url, transport=transport)
                logger.info("Melipayamak SMS client initialized directly")
            
            return True, "Initialized"
        except Exception as e:
            logger.error(f"Failed to initialize SMS client: {e}")
            self.client = None
            return False, str(e)

    def validate_phone_number(self, phone: str) -> Optional[str]:
        """Validate and format Iranian phone number"""
        if not phone:
            return None

        # Remove all non-digit characters
        phone = re.sub(r"[^\d]", "", phone)

        # Check if it's a valid Iranian mobile number
        if phone.startswith("0098"):
            phone = "98" + phone[4:]
        elif phone.startswith("09"):
            phone = "98" + phone[1:]
        elif phone.startswith("98") and len(phone) == 12:
            pass # Already correct
        # Try to see if it's just 10 digits starting with 9
        if len(phone) == 10 and phone.startswith("9"):
            phone = "98" + phone
        
        # Melipayamak usually takes numbers without + prefix and starting with 98 or 09
        # But for international format 989... is safest.
        if not re.match(r"^989\d{9}$", phone):
            logger.warning(f"Invalid Iranian phone number: {phone}")
            return None

        logger.info(f"Phone number formatted to: {phone}")
        return phone

    def get_active_sender_numbers(self) -> list:
        """Get list of active sender numbers for this account from API"""
        try:
            # Try to get senders from API first
            result = self.client.service.GetSenders(
                username=self.username,
                password=self.password
            )
            if result and hasattr(result, 'string'):
                return result.string
            # Fallback if API response is different
            return [str(s) for s in result] if result else []
        except Exception as e:
            logger.error(f"Error getting senders from API: {e}")
            # Last resort hardcoded fallback (the one usually provided by default)
            return ["50002710093953"]

    def send_sms(self, phone: str, message: str) -> Tuple[bool, str]:
        if not self.client:
            success, err = self._initialize_client()
            if not success:
                return False, f"SMS client not initialized: {err}"

        # Validate phone number
        formatted_phone = self.validate_phone_number(phone)
        if not formatted_phone:
            return False, f"Invalid phone number: {phone}"

        try:
            active_senders = self.get_active_sender_numbers()
            
            error_map = {
                "0": "نام کاربری یا رمز عبور اشتباه است",
                "1": "درخواست با موفقیت ثبت شد",
                "2": "اعتبار پنل کافی نیست",
                "3": "محدودیت در تعداد گیرندگان",
                "4": "شماره فرستنده معتبر نیست یا فعال نیست",
                "5": "شماره فرستنده نامعتبر است",
                "6": "سامانه در حال به‌روزرسانی است",
                "7": "متن پیام حاوی کلمات فیلتر شده است",
                "10": "کاربر فعال نیست",
                "11": "ارسال به دلیل فیلترینگ یا لیست سیاه انجام نشد",
                "12": "کاربر مسدود شده است",
            }

            # Try SendSimpleSMS2 with active sender numbers
            last_err = "خطای نامشخص"
            for sender_num in active_senders:
                try:
                    result = self.client.service.SendSimpleSMS2(
                        username=self.username,
                        password=self.password,
                        to=formatted_phone,
                        **{"from": sender_num},
                        text=message,
                        isflash=False,
                    )

                    response_code = str(result)
                    if response_code.isdigit() and int(response_code) > 1000: # RecID
                        logger.info(f"SMS sent: {sender_num}, RecID: {response_code}")
                        return True, f"موفق (کد پیگیری: {response_code})"
                    
                    err_msg = error_map.get(response_code, f"خطای کد {response_code}")
                    logger.warning(f"Failed with sender {sender_num}: {err_msg}")
                    last_err = err_msg
                    continue

                except Exception as e:
                    logger.error(f"Error with sender {sender_num}: {e}")
                    last_err = str(e)
                    continue

            # FALLBACK: Try SendByBaseNumber3 (Shared Service Line)
            logger.info("Attempting fallback with SendByBaseNumber3...")
            try:
                # Note: Corrected parameters based on API signature: username, password, text, to
                result = self.client.service.SendByBaseNumber3(
                    username=self.username,
                    password=self.password,
                    text=message,
                    to=formatted_phone
                )
                response_code = str(result)
                if response_code.isdigit() and int(response_code) > 0:
                    logger.info(f"Fallback via SendByBaseNumber3 successful: {response_code}")
                    return True, f"موفق (از طریق خط خدماتی - کد: {response_code})"
            except Exception as e:
                logger.error(f"Fallback method failed: {e}")

            return False, last_err

        except Exception as e:
            logger.error(f"Error sending SMS to {formatted_phone}: {e}")
            return False, f"Error: {str(e)}"

    def send_interview_reminder(self, db_path: str, interview_id: int, reminder_type: str = "24h") -> Tuple[bool, str]:
        """Send interview reminder SMS based on database record"""
        from . import db
        try:
            # Fetch fresh interview data
            ivs = db.get_interviews(db_path)
            interview = next((i for i in ivs if i["id"] == interview_id), None)
            if not interview:
                return False, "Interview not found"

            # Get case and user phone
            case = db.get_case(db_path, interview["case_id"])
            if not case:
                return False, "Case not found"
            
            # Find the user (direct client or agency)
            user = None
            # Check for direct client first if it's a client case
            with db.connect(db_path) as conn:
                u = conn.execute("SELECT * FROM users WHERE license_code = ? AND role IN ('direct_client', 'agency') LIMIT 1", (case["owner_license_code"],)).fetchone()
                if u:
                    user = dict(u)

            if not user or not user.get("phone"):
                return False, "User phone not found"

            phone = user["phone"]
            client_name = case["client_name"]
            
            # Format datetime
            try:
                dt = datetime.fromisoformat(interview["scheduled_at_iso"])
                date_str = dt.strftime("%Y/%m/%d")
                time_str = dt.strftime("%H:%M")
            except:
                date_str = interview["scheduled_at_iso"]
                time_str = ""

            # Get template
            template_key = f"interview_{reminder_type}"
            if template_key not in self.sms_templates:
                return False, f"Template {template_key} not found"

            message = self.sms_templates[template_key].format(
                client_name=client_name, date=date_str, time=time_str
            )

            # Send SMS
            success, result = self.send_sms(phone, message)

            if success:
                # Update DB
                field = f"sms_sent_{reminder_type}"
                db.update_interview_sms_status(db_path, interview_id, field, datetime.now().isoformat())
                logger.info(f"Interview reminder SMS ({reminder_type}) sent to {phone}")
                return True, f"Sent to {phone}"
            else:
                return False, f"SMS failed: {result}"

        except Exception as e:
            logger.error(f"Error in send_interview_reminder: {e}")
            return False, str(e)

    def send_sms_by_pattern(self, phone: str, pattern_code: str, parameters: list) -> Tuple[bool, str]:
        """Send SMS using a pre-defined pattern (bodyId) in Melipayamak"""
        if not self.client:
            success, err = self._initialize_client()
            if not success:
                return False, f"SMS client not initialized: {err}"

        formatted_phone = self.validate_phone_number(phone)
        if not formatted_phone:
            return False, f"Invalid phone number: {phone}"

        try:
            # Join parameters with ; as required by Melipayamak
            param_str = ";".join(parameters)
            
            result = self.client.service.SendByBaseNumber(
                username=self.username,
                password=self.password,
                text=param_str,
                to=formatted_phone,
                bodyId=int(pattern_code)
            )
            
            response_code = str(result)
            # Melipayamak returns a large number (RecID) on success
            if response_code.isdigit() and int(response_code) > 1000:
                logger.info(f"Pattern SMS sent to {formatted_phone}, RecID: {response_code}")
                return True, f"موفق (کد الگو: {pattern_code}, کد پیگیری: {response_code})"
            
            return False, f"خطای سامانه: {response_code}"
        except Exception as e:
            logger.error(f"Error sending pattern SMS: {e}")
            return False, str(e)

    def test_connection(self) -> Tuple[bool, str]:
        """Test SMS service connection"""
        if not self.client:
            success, err = self._initialize_client()
            if not success: return False, f"Init failed: {err}"

        try:
            result = self.client.service.GetCredit(
                username=self.username, password=self.password
            )
            return True, f"Connection successful. Credit: {result}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"


# Global Instance
sms_service = SMSService()
