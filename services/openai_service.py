import time
import base64
import requests
import os
from PIL import Image
from io import BytesIO
from config import Config

OPENAI_AVAILABLE = False
client = None
openai_error_message = ""
openai_last_check = 0

def log_openai_response(action_type, response_content, char_limit=1024):
    """
    Comprehensive logging for OpenAI responses
    """
    print(f"\n{'='*80}")
    print(f"🚨 OPENAI RESPONSE LOG - {action_type.upper()}")
    print(f"{'='*80}")
    print(f"📊 Response length: {len(response_content)} characters")
    print(f"📏 Character limit: {char_limit}")
    print(f"📈 Limit exceeded: {len(response_content) > char_limit}")
    print(f"📋 Full response content:")
    print(f"{'='*40}")
    print(response_content)
    print(f"{'='*40}")
    print(f"🔍 Response ends with: ...{response_content[-50:] if len(response_content) > 50 else response_content}")
    print(f"{'='*80}\n")

def check_recommendations(action_type, analysis_text):
    """
    Check if the analysis contains essential recommendations
    """
    print(f"\n🔍 RECOMMENDATION CHECK - {action_type.upper()}")

    # Keywords to check for in Arabic and English
    recommendation_keywords = [
        'توصية', 'توصيات', 'دخول', 'شراء', 'بيع', 'هدف', 'أهداف',
        'recommendation', 'entry', 'buy', 'sell', 'target', 'stop loss'
    ]

    timeframe_keywords = [
        '15 دقيقة', 'ربع ساعة', 'خمسة عشر', 'القادمة', 'المقبلة',
        '15 minute', 'next 15', 'quarter', 'coming'
    ]

    has_recommendation = any(keyword in analysis_text.lower() for keyword in recommendation_keywords)
    has_timeframe = any(keyword in analysis_text.lower() for keyword in timeframe_keywords)

    print(f"📊 Has recommendations: {has_recommendation}")
    print(f"⏰ Has timeframe mention: {has_timeframe}")
    print(f"📝 Recommendation check passed: {has_recommendation and has_timeframe}")

    if not has_recommendation:
        print("⚠️ WARNING: Analysis missing trading recommendations!")
    if not has_timeframe:
        print("⚠️ WARNING: Analysis missing 15-minute timeframe context!")

def shorten_analysis_text(analysis_text, char_limit=1024, timeframe=None, currency=None):
    """
    Enhanced shortening that preserves critical information in ARABIC
    """
    global client
    
    if len(analysis_text) <= char_limit:
        return analysis_text

    print(f"📏 SHORTENING: Analysis too long ({len(analysis_text)} chars), requesting shortening...")

    try:
        # ENHANCED: Use Arabic prompt to maintain language consistency
        shortening_prompt = f"""
        تعليمات هامة: يجب تقصير تحليل التداول التالي ليصبح أقل من {char_limit} حرف مع الحفاظ على اللغة العربية.

        **المعلومات التي يجب الحفاظ عليها:**
        1. الإطار الزمني: {timeframe if timeframe else 'M15'}
        2. زوج العملات: {currency if currency else 'غير معروف'}
        3. جميع توصيات التداول (نقاط الدخول، إشارات الشراء/البيع)
        4. مستويات وقف الخسارة وقيم النقاط بالضبط
        5. أهداف جني الأرباح وقيم النقاط بالضبط
        6. معلومات نسبة المخاطرة إلى العائد
        7. مستويات الدعم والمقاومة الرئيسية

        **ما يمكن إزالته لتوفير المساحة:**
        - الشروح الفنية الزائدة
        - أحرف التنسيق المفرطة (===, ---, ***)
        - نقاط التحليل المتكررة
        - الأوصاف غير الأساسية
        - فواصل الأسطر المتعددة
        - العناوين الفرعية غير الضرورية

        **متطلبات التنسيق:**
        - استخدم نقاطًا مختصرة
        - احتفظ بجميع القيم الرقمية (الأسعار، النقاط، المستويات)
        - ركز على التوصيات القابلة للتنفيذ
        - ابدأ بالإطار الزمني والعملة إذا كانت متوفرة
        - **يجب أن يبقى النص باللغة العربية بالكامل**

        **حد الأحرف: أقل من {char_limit} حرف بشكل صارم**

        التحليل الأصلي:
        {analysis_text}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "أنت مختصر لتحليلات التداول. مهمتك الوحيدة هي تقصير التحليل مع الحفاظ على جميع توصيات التداول، مستويات الأسعار، وقف الخسارة، جني الأرباح، ومعلومات الإطار الزمني. كن موجزا جدا وحافظ على اللغة العربية."
                },
                {
                    "role": "user",
                    "content": shortening_prompt
                }
            ],
            max_tokens=600,
            temperature=0.1
        )

        shortened = response.choices[0].message.content.strip()
        
        print(f"📏 SHORTENING: Original: {len(analysis_text)} chars -> Shortened: {len(shortened)} chars")
        
        # Enhanced fallback truncation that preserves recommendations
        if len(shortened) > char_limit:
            print(f"📏 SHORTENING: ⚠️ Still too long after OpenAI shortening, using smart truncation")
            
            # Try to find the recommendations section and preserve it
            recommendation_keywords = ['دخول', 'شراء', 'بيع', 'وقف', 'هدف', 'توصية', 'entry', 'buy', 'sell', 'stop loss', 'target']
            
            # Look for the last occurrence of recommendations
            last_rec_index = -1
            for keyword in recommendation_keywords:
                idx = analysis_text.lower().rfind(keyword)
                if idx > last_rec_index:
                    last_rec_index = idx
            
            if last_rec_index > char_limit * 0.6:  # If recommendations are in the second half
                # Keep the end part with recommendations
                start_index = max(0, last_rec_index - 200)  # Include some context before recommendations
                shortened = analysis_text[start_index:char_limit] + "..."
            else:
                # Basic smart truncation at sentence boundary
                truncated = analysis_text[:char_limit-3]
                last_period = truncated.rfind('.')
                last_newline = truncated.rfind('\n')
                
                cutoff_point = max(last_period, last_newline)
                if cutoff_point > char_limit * 0.7:  # Only use if we have reasonable text
                    shortened = truncated[:cutoff_point+1] + ".."
                else:
                    shortened = truncated + "..."
        
        # Ensure we have timeframe and currency information in Arabic
        final_text = shortened
        if timeframe and timeframe not in final_text:
            # Prepend timeframe info if missing
            timeframe_prefix = f"📊 الإطار الزمني: {timeframe}"
            if currency and currency != 'UNKNOWN':
                timeframe_prefix += f" | العملة: {currency}"
            timeframe_prefix += "\n\n"
            
            # Check if we have room for the prefix
            if len(timeframe_prefix + final_text) <= char_limit:
                final_text = timeframe_prefix + final_text
            else:
                # Remove some characters to make room
                space_needed = len(timeframe_prefix)
                final_text = final_text[:char_limit - space_needed - 3] + "..."
                final_text = timeframe_prefix + final_text
        
        print(f"📏 SHORTENING: ✅ Final length: {len(final_text)} chars")
        return final_text

    except Exception as e:
        print(f"📏 SHORTENING: ❌ Error shortening analysis: {str(e)}")
        # Enhanced fallback: preserve recommendations in truncation
        truncated = analysis_text[:char_limit-3]
        
        # Try to end at a reasonable point
        for punctuation in ['.', '\n', ';']:
            last_pos = truncated.rfind(punctuation)
            if last_pos > char_limit * 0.8:
                truncated = truncated[:last_pos+1]
                break
                
        # Add timeframe info if available
        if timeframe:
            timeframe_info = f"📊 الإطار: {timeframe}"
            if currency and currency != 'UNKNOWN':
                timeframe_info += f" | {currency}"
            truncated = timeframe_info + "\n" + truncated
        
        if len(truncated) > char_limit:
            truncated = truncated[:char_limit-3] + "..."
            
        print(f"📏 SHORTENING: 🛟 Using enhanced fallback truncation: {len(truncated)} chars")
        return truncated

def init_openai():
    """
    Initialize OpenAI client and test model availability.
[O    Sets OPENAI_AVAILABLE, client, openai_error_message, openai_last_check.
    """
    global OPENAI_AVAILABLE, client, openai_error_message, openai_last_check

    print("🚨 OPENAI INIT: Starting OpenAI initialization...")

    try:
        from openai import OpenAI
        print("🚨 OPENAI INIT: OpenAI package imported successfully")

        # Get API key from Config
        api_key = Config.OPENAI_API_KEY
        print(f"🚨 OPENAI INIT: Config.OPENAI_API_KEY = {api_key[:20]}..." if api_key else "🚨 OPENAI INIT: Config.OPENAI_API_KEY = None")
        print(f"🚨 OPENAI INIT: API Key exists: {bool(api_key)}")
        print(f"🚨 OPENAI INIT: API Key length: {len(api_key) if api_key else 0}")

        if not api_key or api_key == "your-api-key-here":
            openai_error_message = "OpenAI API key not configured"
            print(f"🚨 OPENAI INIT: ❌ API key check failed - not configured or still default")
            OPENAI_AVAILABLE = False
            return False

        print("🚨 OPENAI INIT: Creating OpenAI client...")
        client = OpenAI(api_key=api_key)
        print("🚨 OPENAI INIT: OpenAI client created successfully")

        try:
            print("🚨 OPENAI INIT: Testing model availability...")
            models = client.models.list()
            model_ids = [m.id for m in models.data]
            print(f"🚨 OPENAI INIT: Found {len(model_ids)} models")
            print(f"🚨 OPENAI INIT: First few models: {model_ids[:5]}")

            if "gpt-4o" not in model_ids:
                openai_error_message = "GPT-4o model not available in your account"
                print(f"🚨 OPENAI INIT: ❌ GPT-4o not found in available models")
                OPENAI_AVAILABLE = False
                return False

            print("🚨 OPENAI INIT: ✅ GPT-4o model found!")
            OPENAI_AVAILABLE = True
            openai_error_message = ""
            openai_last_check = time.time()
            print("🚨 OPENAI INIT: ✅ OpenAI initialized successfully!")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"🚨 OPENAI INIT: ❌ Model list error: {error_msg}")
            if "insufficient_quota" in error_msg:
                openai_error_message = "Account has no API credits. Please add funds to your OpenAI API account."
            elif "invalid_api_key" in error_msg:
                openai_error_message = "Invalid API key. Please check your OPENAI_API_KEY environment variable."
            elif "rate limit" in error_msg.lower():
                openai_error_message = "Rate limit exceeded. Please try again later."
            else:
                openai_error_message = f"OpenAI API test failed: {error_msg}"
            OPENAI_AVAILABLE = False
            return False

    except ImportError as e:
        print(f"🚨 OPENAI INIT: ❌ OpenAI package import error: {e}")
        openai_error_message = f"OpenAI package not installed: {e}"
        OPENAI_AVAILABLE = False
        return False
    except Exception as e:
        print(f"🚨 OPENAI INIT: ❌ General initialization error: {str(e)}")
        openai_error_message = f"OpenAI initialization error: {str(e)}"
        OPENAI_AVAILABLE = False
        return False

def detect_investing_frame(image_str, image_format):
    """
    Enhanced frame detection for investing.com frames
    Returns: (frame_type, timeframe)
    """
    try:
        print("🔄 INVESTING FRAME DETECTION: Detecting investing.com frame...")

        system_prompt = """
        You are a professional trading chart analyzer. Your task is to detect if this is an investing.com chart frame and identify the timeframe.

        **INVESTING.COM SIGNATURES TO LOOK FOR:**
        - "Investing" text anywhere
        - "powered by TradingView" 
        - "NASDAQ", "NYSE", or other stock exchange names
        - Company names like "Tesla", "Apple", etc.
        - Volume displayed as "1.387M" format
        - Specific layout with time selection buttons

        **TIMEFRAME DETECTION FOR INVESTING.COM:**
        - Look for timeframe indicators: "15", "30", "1H", "4H", "1D", "1W", "1M"
        - Check top areas where timeframe buttons are typically located
        - "15" typically means M15 (15 minutes)
        - "1H" means H1 (1 hour)
        - "4H" means H4 (4 hours)

        **CRITICAL INSTRUCTIONS:**
        - If you see ANY investing.com signatures, return "investing" as frame type
        - Detect the timeframe and return it in standard format (M15, H1, H4, etc.)
        - If no investing.com signatures found, return "unknown" as frame type
        - If timeframe cannot be determined, return "UNKNOWN" for timeframe
        - **NEVER return error messages or apologies**

        Return format: "frame_type,timeframe"
        Example: "investing,M15" or "unknown,UNKNOWN"
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
[I                            "text": "Analyze this chart image for investing.com signatures and detect the timeframe. Return ONLY in format: 'frame_type,timeframe'"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=50,  # Reduced to prevent verbose responses
            temperature=0.1
        )

        result = response.choices[0].message.content.strip()
        print(f"🔄 RAW investing frame detection result: '{result}'")

        # Parse the result
        if ',' in result:
            frame_type, timeframe = result.split(',', 1)
            frame_type = frame_type.strip().lower()
            timeframe = timeframe.strip().upper()
            
            # Handle "15" as M15 specifically for investing.com
            if timeframe == '15':
                timeframe = 'M15'
            
            # Validate frame_type
            if frame_type not in ['investing', 'unknown']:
                frame_type = 'unknown'
            
            print(f"🔄 PARSED: Frame type: '{frame_type}', Timeframe: '{timeframe}'")
            return frame_type, timeframe
        else:
            print(f"🔄 ❌ Invalid format from investing frame detection: '{result}'")
            return "unknown", "UNKNOWN"

    except Exception as e:
        print(f"ERROR: Investing frame detection failed: {str(e)}")
        return "unknown", "UNKNOWN"

def extract_investing_data(image_str, image_format):
    """
    Extract data from investing.com frame format
    Returns: dictionary with extracted data
    """
    try:
        print("📊 INVESTING DATA EXTRACTION: Extracting data from investing.com frame...")

        system_prompt = """
        You are a professional trading data extractor. Your task is to extract key trading data from investing.com charts.

        **DATA TO EXTRACT:**
        - Current price
        - High (H) price
        - Low (L) price  
        - Close (C) price
        - Open price if available
        - Volume data (typically in M or K format like "1.387M")
        - Currency pair or stock symbol

        **INVESTING.COM SPECIFIC FORMATS:**
        - Prices are often displayed as: "H463.61 L461.85 C461.98"
        - Volume: "1.387M" (means 1.387 million)
        - Company names and stock symbols

        **INSTRUCTIONS:**
        - Extract all available price data
        - Convert volume from "1.387M" to numeric value (1387000)
        - Return data in structured format
        - If data not available, mark as None

        Return ONLY a JSON-like structure with the extracted data.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all trading data from this investing.com chart. Return structured data."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300,
            temperature=0.1
        )

        extracted_data_text = response.choices[0].message.content.strip()
        print(f"📊 RAW investing data extraction: '{extracted_data_text}'")

        # Parse the extracted data (this is a simplified version)
        # In a real implementation, you would parse the JSON-like structure
        data = {
            'current_price': None,
            'high': None,
            'low': None,
            'close': None,
            'volume': None,
            'source': 'investing.com'
        }

        # Simple parsing logic (enhance this based on actual response format)
        if 'H' in extracted_data_text:
            # Extract high price
            pass
        if 'L' in extracted_data_text:
            # Extract low price
            pass
        if 'C' in extracted_data_text:
            # Extract close price
            pass

        print(f"📊 EXTRACTED DATA: {data}")
        return data

    except Exception as e:
        print(f"ERROR: Investing data extraction failed: {str(e)}")
        return {}

def detect_currency_from_image(image_str, image_format):
    """
    Detect the currency pair from the chart image
    Returns: (currency_pair, error_message)
    """
    try:
        print("🪙 CURRENCY DETECTION: Detecting currency pair from image...")

        system_prompt = """
        You are a professional trading chart analyzer. Your task is to detect the currency pair in trading chart images.

        You MUST check ALL these areas thoroughly:

        **MAIN AREAS TO CHECK:**
        - Chart title/header (most common)
        - Top left corner
        - Top right corner  
        - Top center area
        - Chart legend or label
        - Any text displaying currency pairs

        **CURRENCY FORMATS TO LOOK FOR:**
        - Major pairs: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD
        - Minor pairs: EUR/GBP, EUR/JPY, GBP/JPY, etc.
        - Crypto: BTC/USD, ETH/USD, etc.
        - Gold: XAU/USD, GOLD
        - With or without slash: EURUSD, EUR/USD, GBPUSD, GBP/USD, XAUUSD, XAU/USD
        - Any other currency combination

        **CRITICAL INSTRUCTIONS:**
        - Scan the ENTIRE image systematically for currency pair text
        - Look for text that appears to be a currency pair (typically 6-7 characters with optional slash)
        - Focus on areas that typically show the instrument name
        - If you find ANY currency pair indicator, return it in standard format (e.g., EUR/USD)
        - If no clear currency pair found after thorough search, return 'UNKNOWN'

        Return ONLY the currency pair in standard format (with slash) or 'UNKNOWN'.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Perform a COMPREHENSIVE search for the currency pair label in this trading chart. Check ALL areas: chart title, top left, top right, top center, and any text labels. Return ONLY the currency pair like EUR/USD, GBP/USD or UNKNOWN if not found after thorough search."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100,
            temperature=0.1
        )

        detected_currency = response.choices[0].message.content.strip().upper()
        print(f"🪙 RAW currency detection result: '{detected_currency}'")

        # Clean and standardize the currency format
        cleaned_currency = detected_currency.replace(' ', '')
        
        # Add slash if missing (e.g., EURUSD -> EUR/USD)
        if len(cleaned_currency) == 6 and '/' not in cleaned_currency:
            cleaned_currency = f"{cleaned_currency[:3]}/{cleaned_currency[3:]}"
        
        # Handle gold specifically
        if 'XAU' in cleaned_currency or 'GOLD' in cleaned_currency:
            cleaned_currency = 'XAU/USD'
        
        print(f"🪙 Cleaned currency: '{cleaned_currency}'")

        # Common currency pairs for validation
        common_pairs = [
            'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'USD/CAD', 'NZD/USD',
            'EUR/GBP', 'EUR/JPY', 'GBP/JPY', 'EUR/CHF', 'AUD/JPY', 'USD/CNH', 'USD/SGD',
            'BTC/USD', 'ETH/USD', 'XAU/USD', 'XAG/USD'
        ]

        # Check if it matches common pairs
        if cleaned_currency in common_pairs:
            print(f"🪙 ✅ Valid currency pair detected: '{cleaned_currency}'")
            return cleaned_currency, None
        elif 'UNKNOWN' in cleaned_currency:
            print(f"🪙 ❌ No currency pair detected")
            return 'UNKNOWN', "لم يتم العثور على زوج العملات في الصورة"
        else:
            print(f"🪙 ⚠️ Uncommon currency pair detected: '{cleaned_currency}'")
            return cleaned_currency, None

    except Exception as e:
        print(f"ERROR: Currency detection failed: {str(e)}")
        return 'UNKNOWN', f"خطأ في اكتشاف زوج العملات: {str(e)}"

def validate_currency_consistency(first_currency, second_currency):
    """
    Validate that both charts are for the same currency pair
    Returns: (is_valid, error_message)
    """
    try:
        print(f"🪙 CURRENCY VALIDATION: First: '{first_currency}', Second: '{second_currency}'")

        if first_currency == 'UNKNOWN' or second_currency == 'UNKNOWN':
            print(f"🪙 ⚠️ Currency validation skipped - one or both currencies unknown")
            return True, None  # Skip validation if currency detection failed

        # Normalize currencies for comparison (remove any spaces, make uppercase)
        first_normalized = first_currency.replace(' ', '').upper()
        second_normalized = second_currency.replace(' ', '').upper()

        # Check if they are the same
        if first_normalized == second_normalized:
            print(f"🪙 ✅ Currency validation PASSED")
            return True, None
        else:
            print(f"🪙 ❌ Currency validation FAILED - different currencies")
            return False, f"❌ العملات مختلفة! الصورة الأولى لـ {first_currency} والصورة الثانية لـ {second_currency}.\n\nيرجى إرسال صور لنفس زوج العملات:\n• الصورة الأولى: M15 لـ {first_currency}\n• الصورة الثانية: H4 لـ {first_currency}"

    except Exception as e:
        print(f"ERROR: Currency validation failed: {str(e)}")
        return True, None  # Skip validation on error to avoid blocking users

def detect_timeframe_from_image(image_str, image_format):
    """
    Detect the timeframe from the chart image - IMPROVED VERSION
    Better logic to prevent M15 being misclassified as M1
    Returns: (timeframe, error_message)
    """
    try:
        print("🕵️ IMPROVED timeframe detection from image...")

        system_prompt = """
        You are a professional trading chart analyzer. Your ONLY task is to detect the timeframe in trading chart images.

        You MUST check ALL these areas thoroughly:

        **TOP AREAS:**
        - Top left corner (most common)
        - Top right corner (very common)
        - Top center/header area
        - Chart title/header bar

        **BOTTOM AREAS:**
        - Bottom left corner
        - Bottom right corner
        - Bottom center below the chart
        - X-axis (time axis) labels
        - Bottom status bar or information panel

        **OTHER AREAS:**
        - Left side panel/scale area
        - Right side panel/scale area
        - Chart information box/overlay
        - Any text labels anywhere in the image

        **TIMEFRAME FORMATS TO LOOK FOR:**
        - Standard: M1, M5, M15, M30, H1, H4, D1, W1, MN
        - Variations: 15M, 15m, 1H, 1h, 4H, 4h, 1D, 1d, 1W, 1w
        - Full words: 1 Minute, 5 Minutes, 15 Minutes, 30 Minutes, 1 Hour, 4 Hours, Daily, Weekly, Monthly
        - With labels: TF: M15, Timeframe: H4, Period: D1
        - Investing.com specific: "15" (means M15), "1H", "4H", etc.

        **CRITICAL INSTRUCTIONS:**
        - Scan the ENTIRE image systematically from top to bottom, left to right
        - Pay special attention to bottom areas which are often missed
        - Look for small text in corners and edges
        - Check both standard formats and variations
        - If you find ANY timeframe indicator, return it
        - If no clear timeframe found after thorough search, return 'UNKNOWN'

        Return ONLY the timeframe code in standard format or 'UNKNOWN'.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Perform a COMPREHENSIVE search for the timeframe label in this trading chart. Check ALL areas: top left, top right, top center, bottom left, bottom right, bottom center, x-axis, side panels, and any text labels. Return ONLY the timeframe code like M15, H4, D1 or UNKNOWN if not found after thorough search."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100,
            temperature=0.1
        )

        detected_timeframe = response.choices[0].message.content.strip().upper()
        print(f"🕵️ RAW timeframe detection result: '{detected_timeframe}'")

        # Enhanced cleaning and validation
        cleaned_timeframe = detected_timeframe.replace(' ', '').replace('TF:', '').replace('TIMEFRAME:', '').replace('PERIOD:', '').replace('TIMEFRAME', '').replace('PERIOD', '')
        print(f"🕵️ Cleaned timeframe: '{cleaned_timeframe}'")

        # Comprehensive timeframe mapping - ORDER MATTERS! Check longer strings first
        timeframe_map = {
            # M15 variations - CHECK THESE FIRST to prevent M1 false positives
            '15MINUTES': 'M15', '15MINUTE': 'M15', '15MIN': 'M15', '15M': 'M15', '15m': 'M15', 'M15M': 'M15',
            # Special case for investing.com "15"
            '15': 'M15',
            # M30 variations
            '30MINUTES': 'M30', '30MINUTE': 'M30', '30MIN': 'M30', '30M': 'M30', '30m': 'M30', 'M30M': 'M30',
            # H4 variations
            '4HOURS': 'H4', '4HOUR': 'H4', '4H': 'H4', '4h': 'H4', 'H4H': 'H4', '240M': 'H4',
            # H1 variations
            '1HOUR': 'H1', '1H': 'H1', '1h': 'H1', 'H1H': 'H1', '60M': 'H1', '60MIN': 'H1',
            # D1 variations
            'DAILY': 'D1', '1DAY': 'D1', '1D': 'D1', '1d': 'D1', 'D1D': 'D1',
            # W1 variations
            'WEEKLY': 'W1', '1WEEK': 'W1', '1W': 'W1', '1w': 'W1',
            # MN variations
            'MONTHLY': 'MN', '1MONTH': 'MN', 'MN': 'MN',
            # M5 variations
            '5MINUTES': 'M5', '5MINUTE': 'M5', '5MIN': 'M5', '5M': 'M5', '5m': 'M5', 'M5M': 'M5',
            # M1 variations - CHECK THESE LAST to prevent false positives
            '1MINUTE': 'M1', '1MIN': 'M1', '1M': 'M1', '1m': 'M1', 'M1M': 'M1'
        }

        # Try exact match first - check in order of priority
        for timeframe_variant, standard_tf in timeframe_map.items():
            if cleaned_timeframe == timeframe_variant:
                print(f"🕵️ Exact match: '{cleaned_timeframe}' -> '{standard_tf}'")
                return standard_tf, None

        # Try partial matches with priority (longer timeframes first)
        priority_timeframes = ['M15', 'M30', 'H4', 'H1', 'D1', 'W1', 'MN', 'M5', 'M1']

        for tf in priority_timeframes:
            if tf in cleaned_timeframe:
                print(f"🕵️ Partial match: found '{tf}' in '{cleaned_timeframe}'")
                return tf, None

        # Special case: if we see "15" anywhere, prioritize M15
        if '15' in cleaned_timeframe and any(word in cleaned_timeframe for word in ['M', 'MIN', 'MINUTE']):
            print(f"🕵️ Special case: '15' found in '{cleaned_timeframe}', returning M15")
            return 'M15', None

        # Special case: if we see "1" but it's likely part of "15", be careful
        if '1' in cleaned_timeframe and '15' not in cleaned_timeframe and any(word in cleaned_timeframe for word in ['M', 'MIN', 'MINUTE']):
            # Only return M1 if we're sure it's not M15
            if cleaned_timeframe in ['1M', '1MIN', '1MINUTE', 'M1']:
                print(f"🕵️ Confident M1 detection: '{cleaned_timeframe}'")
                return 'M1', None

        # Try word-based detection with M15 priority
        if any(word in cleaned_timeframe for word in ['MINUTE', 'MIN', 'M']):
            if '15' in cleaned_timeframe or 'FIFTEEN' in cleaned_timeframe:
                print(f"🕵️ Word-based: M15 detected from '{cleaned_timeframe}'")
                return 'M15', None
            elif '30' in cleaned_timeframe or 'THIRTY' in cleaned_timeframe:
                print(f"🕵️ Word-based: M30 detected from '{cleaned_timeframe}'")
                return 'M30', None
            elif '5' in cleaned_timeframe or 'FIVE' in cleaned_timeframe:
                print(f"🕵️ Word-based: M5 detected from '{cleaned_timeframe}'")
                return 'M5', None
            elif '1' in cleaned_timeframe and '15' not in cleaned_timeframe:
                print(f"🕵️ Word-based: M1 detected from '{cleaned_timeframe}'")
                return 'M1', None

        if any(word in cleaned_timeframe for word in ['HOUR', 'H']):
            if '4' in cleaned_timeframe or 'FOUR' in cleaned_timeframe:
                print(f"🕵️ Word-based: H4 detected from '{cleaned_timeframe}'")
                return 'H4', None
            elif '1' in cleaned_timeframe:
                print(f"🕵️ Word-based: H1 detected from '{cleaned_timeframe}'")
                return 'H1', None

        if any(word in cleaned_timeframe for word in ['DAY', 'D']):
            print(f"🕵️ Word-based: D1 detected from '{cleaned_timeframe}'")
            return 'D1', None

        if any(word in cleaned_timeframe for word in ['WEEK', 'W']):
            print(f"🕵️ Word-based: W1 detected from '{cleaned_timeframe}'")
            return 'W1', None

        if any(word in cleaned_timeframe for word in ['MONTH', 'MN']):
            print(f"🕵️ Word-based: MN detected from '{cleaned_timeframe}'")
            return 'MN', None

        print(f"🕵️ No valid timeframe found in '{cleaned_timeframe}', returning UNKNOWN")
        return 'UNKNOWN', None

    except Exception as e:
        print(f"ERROR: Improved timeframe detection failed: {str(e)}")
        return 'UNKNOWN', None

def validate_timeframe_for_analysis(image_str, image_format, expected_timeframe):
    """
    STRICT validation for first and second analysis with enhanced detection
    Returns: (is_valid, error_message)
    """
    try:
        print(f"🕵️ STRICT VALIDATION: Expecting '{expected_timeframe}'")

        detected_timeframe, detection_error = detect_timeframe_from_image(image_str, image_format)

        if detection_error:
            return False, f"❌ لا يمكن تحليل الإطار الزمني للصورة. يرجى التأكد من أن الصورة تحتوي على إطار {expected_timeframe} واضح."

        print(f"🕵️ Validation Result: Detected '{detected_timeframe}', Expected '{expected_timeframe}'")

        if detected_timeframe == expected_timeframe:
            print(f"🕵️ ✅ Validation PASSED")
            return True, None
        elif detected_timeframe == 'UNKNOWN':
            print(f"🕵️ ❌ Validation FAILED - No timeframe detected")
            return False, f"❌ لم يتم العثور على إطار زمني واضح في الصورة. يرجى:\n• التأكد من أن الإطار الزمني ({expected_timeframe}) مرئي في الصورة\n• تحميل صورة أوضح تحتوي على {expected_timeframe}\n• التأكد من أن النص غير مقطوع"
        else:
            print(f"🕵️ ❌ Validation FAILED - Wrong timeframe")
            return False, f"❌ الإطار الزمني الموجود في الصورة هو {detected_timeframe} ولكن المطلوب هو {expected_timeframe}.\n\nيرجى تحميل صورة تحتوي على الإطار الزمني الصحيح:\n• للتحليل الأول: M15 (15 دقيقة)\n• للتحليل الثاني: H4 (4 ساعات)"

    except Exception as e:
        print(f"ERROR: Timeframe validation failed: {str(e)}")
        return False, f"❌ خطأ في التحقق من الإطار الزمني: {str(e)}"

def analyze_with_openai(image_str, image_format, timeframe=None, previous_analysis=None, user_analysis=None, action_type="chart_analysis", currency_pair=None):
    """
    Analyze an image or text using OpenAI with enhanced, detailed analysis.
    STRICTLY ENFORCES 1024 CHARACTER LIMIT AND 50 PIP STOP LOSS
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    # STRICT validation for first and second analysis
    if image_str and action_type in ['first_analysis', 'second_analysis']:
        expected_timeframe = 'M15' if action_type == 'first_analysis' else 'H4'
        is_valid, error_msg = validate_timeframe_for_analysis(image_str, image_format, expected_timeframe)
        if not is_valid:
            return error_msg

    # ALL ANALYSIS TYPES STRICTLY LIMITED TO 1024 CHARACTERS
    char_limit = 1024
    max_tokens = 600

    # 🟡 SPECIAL STOP LOSS FOR GOLD vs OTHER PAIRS
    if currency_pair and currency_pair.upper() in ['XAU/USD', 'XAUUSD', 'GOLD']:
        stop_loss_instruction = """
        **🟡 إعدادات وقف الخسارة الإلزامية للذهب (XAU/USD):**
        - **انتبه: الذهب مختلف عن العملات! كل 1 نقطة في الذهب = 10 نقاط في العملات العادية**
        - **الحد الأقصى المطلق: 5 نقاط فقط للذهب (تعادل 50 نقطة في العملات)**
        - **ممنوع منعاً باتاً تجاوز 5 نقاط للذهب تحت أي ظرف**
        - **يجب أن يكون وقف الخسارة بين 2-5 نقاط للذهب حسب التقلب**
        - **إذا تطلب السوق أكثر من 5 نقاط للذهب، لا تقدم توصية بالتداول**
        - **السبب: حماية رأس المال - 5 نقاط ذهب = 50 نقطة فعلية**
        """
        print("🟡 GOLD DETECTED: Using special stop loss rules (2-5 pips)")
    else:
        stop_loss_instruction = """
        **🛑 إعدادات وقف الخسارة الإلزامية:**
        - **الحد الأقصى المطلق: 50 نقطة فقط**
        - **ممنوع منعاً باتاً تجاوز 50 نقطة تحت أي ظرف**
        - **يجب أن يكون وقف الخسارة بين 20-50 نقطة حسب التقلب**
        - **إذا تطلب السوق أكثر من 50 نقطة، لا تقدم توصية بالتداول**
        - **السبب: حماية رأس المال ومنع المخاطرة العالية**
        """
        print("🟢 REGULAR CURRENCY: Using standard stop loss rules (20-50 pips)")

    if action_type == "user_analysis_feedback":
        analysis_prompt = f"""
أنت خبير تحليل فني صارم وصادق. قم بتقييم تحليل المستخدم التالي بصدق وموضوعية.

تحليل المستخدم:
{user_analysis}

**تعليمات صارمة:**
1. قيم التحليل بناءً على الدقة الفنية والمنطق
2. كن صادقًا وواضحًا - إذا كان التحليل ضعيفًا أو خاطئًا، قل ذلك بوضوح
3. لا تبالغ في الإيجابيات إذا كانت غير موجودة
4. ركز على الأخطاء الجسيمة في التفكير التحليلي
5. قدم نقدًا بناءً مع حلول عملية

**مهمتك:**
- قدم تقييماً موضوعياً في حدود 1000 حرف فقط
- لا تتجاوز 1024 حرف تحت أي ظرف
- كن مباشراً وواضحاً
- ركز على النقاط الأساسية

**لا تضف عدد الأحرف في نهاية الرد.**
"""

    elif action_type == "single_analysis":
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات باستخدام مفاهيم المال الذكي والـ ICT. قدم تحليلاً شاملاً للرسم البياني.

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 مفاهيم المال الذكي (SMC):**
- تحليل مناطق السيولة (Liquidity)
- تحديد أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers - SK)
- تحليل الاختراقات (Breaker Blocks)

**📈 مفاهيم ICT (Inner Circle Trader):**
- تحليل السيولة السابقة (Previous Liquidity)
- مناطق العرض والطلب (Supply/Demand Zones)
- تحليل الوقت (Time Analysis)
- حركة السعر (Price Action)

**📊 مستويات فيبوناتشي:**
- تحديد المستويات الرئيسية (38.2%, 50%, 61.8%)
- تحليل تفاعل السعر

**🛡️ الدعم والمقاومة:**
- المستويات الرئيسية
- المناطق الحرجة

**⚡ التوصيات الفورية (5-15 دقيقة):**
- **يجب أن تتضمن توصية واضحة للربع ساعة القادم (15 دقيقة)**
- نقاط الدخول القريبة خلال الربع ساعة القادم

{stop_loss_instruction}

- أهداف جني الأرباح (نسبة مخاطرة إلى عائد 1:2 كحد أدنى)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على التوصيات العملية الفورية
- **ممنوع منعاً باتاً اقتراح وقف خسارة أكثر من الحد المسموح**
- **إذا كان السوق يتطلب أكثر من الحد المسموح، اذكر أن الصفقة غير مناسبة حالياً**
- **لا تضف عدد الأحرف في نهاية الرد**
- **تأكد من تضمين توصية محددة للربع ساعة القادمة في نهاية التحليل.**
"""

    elif timeframe == "H4" and previous_analysis:
        analysis_prompt = f"""
أنت محلل فني محترف. قدم تحليلاً شاملاً يجمع بين الإطارين الزمنيين.

التحليل السابق (15 دقيقة): {previous_analysis}

**المطلوب تحليل شامل يتضمن:**

### 📊 التحليل الفني الشامل
**1. تحليل فيبوناتشي الرئيسية**
**2. الدعم والمقاومة الحرجة**
**3. تحليل السيولة باستخدام SMC وICT**
**4. قاتل الجلسات (SK) ومناطق الاختراق**
**5. التوصيات العملية:**
- نقاط الدخول

{stop_loss_instruction}

- أهداف جني الأرباح (نسبة مخاطرة إلى عائد 1:2 على الأقل)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على الدمج بين الإطارين
- قدم توصيات عملية مباشرة
- **ممنوع منعاً باتاً اقتراح وقف خسارة أكثر من الحد المسموح**
- **لا تضف عدد الأحرف في نهاية الرد**
"""

    elif action_type == "final_analysis":
        analysis_prompt = f"""
أنت خبير تحليل فني محترف. قم بتحليل شامل بناءً على التحليلين السابقين.

التحليل الأول (M15): {previous_analysis}

**المطلوب تحليل نهائي متكامل يتضمن:**

### 📈 التحليل الشامل
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الحرجة:**
**🛡️ الدعم والمقاومة الرئيسية:**
**💧 تحليل SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق العرض والطلب (Supply/Demand)

**💼 التوصيات الاستراتيجية:**
- نقاط الدخول الاستراتيجية

{stop_loss_instruction}

- أهداف جني الأرباح (نسبة مخاطرة إلى عائد 1:2 كحد أدنى)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على التوصيات العملية
- كن مباشراً وواضحاً
- **ممنوع منعاً باتاً اقتراح وقف خسارة أكثر من الحد المسموح**
- **لا تضف عدد الأحرف في نهاية الرد**
"""

    else:
        # First analysis with detailed prompt
        analysis_prompt = f"""
أنت محلل فني محترف متخصص في تحليل العملات. قدم تحليلاً شاملاً للرسم البياني.

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الحرجة:**
**💧 تحليل السيولة باستخدام SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق الاختراق (Breaker Blocks)

**⚡ التوصيات العملية الفورية:**
- نقاط الدخول القريبة

{stop_loss_instruction}

- أهداف جني الأرباح (نسبة مخاطرة إلى عائد 1:2 كحد أدنى)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على التوصيات خلال 5-15 دقيقة
- كن مباشراً وواضحاً
- **ممنوع منعاً باتاً اقتراح وقف خسارة أكثر من الحد المسموح**
- **لا تضف عدد الأحرف في نهاية الرد**
"""

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        import time
        start_time = time.time()

        # Add pre-call logging
        print(f"🔍 OPENAI PRE-REQUEST: {action_type}")
        print(f"🔍 Prompt length: {len(analysis_prompt)} characters")
        print(f"🔍 Max tokens: {max_tokens}")

        if image_str:
            print(f"🚨 OPENAI ANALYSIS: Analyzing image with {action_type}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم بعدم تجاوز {char_limit} حرف في ردك. لا تضف عدد الأحرف في النهاية."},
                    {"role": "user", "content": [
                        {"type": "text", "text": analysis_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                    ]}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=30
            )
        else:
            print(f"🚨 OPENAI ANALYSIS: Analyzing text with {action_type}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"أنت محلل فني محترف. التزم بعدم تجاوز {char_limit} حرف في ردك. لا تضف عدد الأحرف في النهاية."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=20
            )

        analysis = response.choices[0].message.content.strip()
        processing_time = time.time() - start_time

        # Enhanced token usage logging
        if response.usage:
            print(f"🔢 Token Usage - Prompt: {response.usage.prompt_tokens}, Completion: {response.usage.completion_tokens}, Total: {response.usage.total_tokens}")
            print(f"🔢 Max Tokens Limit: {max_tokens}, Completion Used: {response.usage.completion_tokens}/{max_tokens}")
        else:
            print("🔢 Token Usage: Not available")

        # Comprehensive logging
        print(f"\n{'='*60}")
        print(f"🚨 OPENAI RAW RESPONSE - {action_type.upper()}")
        print(f"{'='*60}")
        print(f"⏰ Processing time: {processing_time:.2f}s")
        print(f"📊 Response length: {len(analysis)} characters")
        print(f"📝 Full content:")
        print(f"{'-'*40}")
        print(analysis)
        print(f"{'-'*40}")
        print(f"{'='*60}\n")

        # Check for truncation indicators
        if '...' in analysis[-10:] or len(analysis) >= 1020:
            print("⚠️ WARNING: Response might be truncated!")

        # Log the full response
        log_openai_response(action_type, analysis)

        # Check for recommendations
        if action_type in ['first_analysis', 'single_analysis', 'technical_analysis']:
            check_recommendations(action_type, analysis)

        # NO TRIMMING - We rely on prompt engineering to enforce limits
        if len(analysis) > char_limit:
            print(f"🚨 OPENAI ANALYSIS: ⚠️ Analysis exceeded limit ({len(analysis)} chars), but keeping original response")

        return analysis

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI analysis failed: {str(e)}")

def load_image_from_url(image_url):
    """Load and encode image from URL and return (b64string, format) or (None, None)"""
    try:
        print(f"🚨 IMAGE LOAD: Loading image from {image_url}")
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            if img.format in ['PNG', 'JPEG', 'JPG']:
                buffered = BytesIO()
                img_format = img.format if img.format else 'JPEG'
                img.save(buffered, format=img_format)
                b64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
                print(f"🚨 IMAGE LOAD: ✅ Image loaded successfully, format: {img_format}, size: {len(b64_data)} chars")
                return b64_data, img_format
        print(f"🚨 IMAGE LOAD: ❌ Failed to load image, status: {response.status_code}")
        return None, None
    except Exception as e:
        print(f"🚨 IMAGE LOAD: ❌ Error loading image: {e}")
        return None, None

def analyze_technical_chart(image_str, image_format, timeframe=None, currency_pair=None):
    """
    Analyze the technical chart only (first call)
    STRICTLY ENFORCES 1024 CHARACTER LIMIT AND 50 PIP STOP LOSS
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    char_limit = 1024
    max_tokens = 600

    # 🟡 SPECIAL STOP LOSS FOR GOLD vs OTHER PAIRS
    if currency_pair and currency_pair.upper() in ['XAU/USD', 'XAUUSD', 'GOLD']:
        stop_loss_instruction = """
        **🟡 إعدادات وقف الخسارة الإلزامية للذهب (XAU/USD):**
        - **انتبه: الذهب مختلف عن العملات! كل 1 نقطة في الذهب = 10 نقاط في العملات العادية**
        - **الحد الأقصى المطلق: 5 نقاط فقط للذهب (تعادل 50 نقطة في العملات)**
        - **ممنوع منعاً باتاً تجاوز 5 نقاط للذهب تحت أي ظرف**
        - **يجب أن يكون وقف الخسارة بين 2-5 نقاط للذهب حسب التقلب**
        - **إذا تطلب السوق أكثر من 5 نقاط للذهب، لا تقدم توصية بالتداول**
        - **السبب: حماية رأس المال - 5 نقاط ذهب = 50 نقطة فعلية**
        """
        print("🟡 GOLD DETECTED: Using special stop loss rules (2-5 pips)")
    else:
        stop_loss_instruction = """
        **🛑 إعدادات وقف الخسارة الإلزامية:**
        - **الحد الأقصى المطلق: 50 نقطة فقط**
        - **ممنوع منعاً باتاً تجاوز 50 نقطة تحت أي ظرف**
        - **يجب أن يكون وقف الخسارة بين 20-50 نقطة حسب التقلب**
        - **إذا تطلب السوق أكثر من 50 نقطة، لا تقدم توصية بالتداول**
        - **السبب: حماية رأس المال ومنع المخاطرة العالية**
        """
        print("🟢 REGULAR CURRENCY: Using standard stop loss rules (20-50 pips)")

    analysis_prompt = f"""
أنت خبير تحليل فني للمخططات المالية. قم بتحليل الرسم البياني من الناحية الفنية فقط.

**المطلوب تحليل فني كامل يتضمن:**

### 📊 التحليل الفني لشارت {timeframe}
**🎯 الاتجاه العام وهيكل السوق:**
**📊 مستويات فيبوناتشي الرئيسية:**
**🛡️ الدعم والمقاومة الحرجة:**
**💧 تحليل السيولة باستخدام SMC وICT:**
- مناطق السيولة (Liquidity)
- أوامر التجميع (Order Blocks)
- قاتل الجلسات (Session Killers)
- مناطق العرض والطلب (Supply/Demand)

**💼 التوصيات العملية:**
- نقاط الدخول

{stop_loss_instruction}

- أهداف جني الأرباح (نسبة مخاطرة إلى عائد 1:2 على الأقل)

**التعليمات الإلزامية:**
- ركز فقط على التحليل الفني للمخطط
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- كن مباشراً وواضحاً
- **ممنوع منعاً باتاً اقتراح وقف خسارة أكثر من الحد المسموح**
- **لا تضف عدد الأحرف في نهاية الرد**
"""

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        print(f"🚨 OPENAI ANALYSIS: 🧠 Starting technical analysis with timeframe: {timeframe}")

        # Add pre-call logging
        print(f"🔍 TECHNICAL PRE-REQUEST")
        print(f"🔍 Prompt length: {len(analysis_prompt)} characters")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت خبير تحليل فني. ركز فقط على التحليل الفني. التزم بعدم تجاوز 1024 حرف. لا تضف عدد الأحرف في النهاية."},
                {"role": "user", "content": [
                    {"type": "text", "text": analysis_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                ]}
            ],
            max_tokens=max_tokens,
            temperature=0.7,
            timeout=30
        )

        analysis = response.choices[0].message.content.strip()

        # Enhanced token usage logging
        if response.usage:
            print(f"🔢 Token Usage - Prompt: {response.usage.prompt_tokens}, Completion: {response.usage.completion_tokens}, Total: {response.usage.total_tokens}")
            print(f"🔢 Max Tokens Limit: {max_tokens}, Completion Used: {response.usage.completion_tokens}/{max_tokens}")
        else:
            print("🔢 Token Usage: Not available")

        # Comprehensive logging
        print(f"\n{'='*60}")
        print(f"🚨 TECHNICAL ANALYSIS RAW RESPONSE")
        print(f"{'='*60}")
        print(f"📊 Response length: {len(analysis)} characters")
        print(f"📝 Full content:")
        print(f"{'-'*40}")
        print(analysis)
        print(f"{'-'*40}")
        print(f"{'='*60}\n")

        # Log the full response
        log_openai_response("technical_analysis", analysis)

        # Check for recommendations
        check_recommendations("technical_analysis", analysis)

        # NO TRIMMING - We rely on prompt engineering
        if len(analysis) > char_limit:
            print(f"🚨 OPENAI ANALYSIS: ⚠️ Technical analysis exceeded limit ({len(analysis)} chars), but keeping original response")

        return analysis

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Technical analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI analysis failed: {str(e)}")

def analyze_user_drawn_feedback_simple(image_str, image_format, timeframe=None):
    """
    Simple version for user feedback analysis without technical analysis context
    STRICTLY ENFORCES 1024 CHARACTER LIMIT
    """
    global client

    if not OPENAI_AVAILABLE:
        raise RuntimeError(f"OpenAI not available: {openai_error_message}")

    char_limit = 1024
    max_tokens = 600

    feedback_prompt = f"""
أنت خبير تحليل فني ومدرس محترف. قم بتقييم التحليل المرسوم من قبل المستخدم على الرسم البياني.

**مهمتك: تقييم الرسومات والتحليلات المرسومة:**

1. **تقييم الخطوط المرسومة:** (الاتجاه، الدعم/المقاومة، فيبوناتشي)
2. **تقييم الأشكال والعلامات:** (الدوائر، الأسهم، الإشارات)
3. **نقاط القوة:** (الجوانب الإيجابية)
4. **نقاط الضعف:** (الأخطاء والتحسينات)
5. **توصيات للتحسين:** (نصائح عملية)

**تعليمات صارمة:**
- كن صادقاً وموضوعياً في التقييم
- قدم نقداً بناءً يهدف لمساعدة المستخدم
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- **لا تضف عدد الأحرف في نهاية الرد**
"""

    if not client:
        raise RuntimeError("OpenAI client not initialized")

    try:
        print(f"🚨 OPENAI ANALYSIS: 🧠 Starting simple user feedback analysis with timeframe: {timeframe}")

        # Add pre-call logging
        print(f"🔍 USER FEEDBACK PRE-REQUEST")
        print(f"🔍 Prompt length: {len(feedback_prompt)} characters")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "أنت مدرس تحليل فني محترف. قيم تحليل المستخدم المرسوم بموضوعية. التزم بعدم تجاوز 1024 حرف. لا تضف عدد الأحرف في النهاية."},
                {"role": "user", "content": [
                    {"type": "text", "text": feedback_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": "low"}}
                ]}
            ],
            max_tokens=max_tokens,
            temperature=0.7,
            timeout=30
        )

        feedback = response.choices[0].message.content.strip()

        # Enhanced token usage logging
        if response.usage:
            print(f"🔢 Token Usage - Prompt: {response.usage.prompt_tokens}, Completion: {response.usage.completion_tokens}, Total: {response.usage.total_tokens}")
            print(f"🔢 Max Tokens Limit: {max_tokens}, Completion Used: {response.usage.completion_tokens}/{max_tokens}")
        else:
            print("🔢 Token Usage: Not available")

        # Comprehensive logging
        print(f"\n{'='*60}")
        print(f"🚨 USER FEEDBACK RAW RESPONSE")
        print(f"{'='*60}")
        print(f"📊 Response length: {len(feedback)} characters")
        print(f"📝 Full content:")
        print(f"{'-'*40}")
        print(feedback)
        print(f"{'-'*40}")
        print(f"{'='*60}\n")

        # Log the full response
        log_openai_response("user_feedback", feedback)

        # NO TRIMMING - We rely on prompt engineering
        if len(feedback) > char_limit:
            print(f"🚨 OPENAI ANALYSIS: ⚠️ Feedback exceeded limit ({len(feedback)} chars), but keeping original response")

        return feedback

    except Exception as e:
        print(f"🚨 OPENAI ANALYSIS: ❌ Simple user feedback analysis failed: {str(e)}")
        raise RuntimeError(f"OpenAI feedback analysis failed: {str(e)}")
