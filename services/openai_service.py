import time
import base64
import requests
import os
import re
from PIL import Image
from io import BytesIO
from config import Config

OPENAI_AVAILABLE = False
client = None
openai_error_message = ""
openai_last_check = 0
VISION_IMAGE_DETAIL = "high"


def canonicalize_instrument_symbol(symbol):
    if not symbol:
        return 'UNKNOWN'

    cleaned_symbol = str(symbol).replace(' ', '').replace('/', '').upper()
    if cleaned_symbol in ['UNKNOWN', 'NOTFOUND', '']:
        return 'UNKNOWN'

    quote_currencies = {'USD', 'EUR', 'JPY', 'GBP', 'CHF', 'AUD', 'CAD', 'NZD'}
    if len(cleaned_symbol) == 6 and cleaned_symbol.isalpha() and cleaned_symbol[3:] in quote_currencies:
        return f"{cleaned_symbol[:3]}/{cleaned_symbol[3:]}"

    return cleaned_symbol

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
    CONSERVATIVE shortening that preserves ALL critical trading information in ARABIC
    Targets 980-1024 characters range while keeping essential data
    """
    global client
    
    if len(analysis_text) <= char_limit:
        return analysis_text

    print(f"📏 CONSERVATIVE SHORTENING: Analysis slightly long ({len(analysis_text)} chars), optimizing...")

    try:
        # CONSERVATIVE PROMPT - Only remove non-essential parts
        shortening_prompt = f"""
        مهمتك: تقصير تحليل التداول التالي قليلاً فقط ليصبح بين 980 و 1024 حرف مع الحفاظ على كل المعلومات الأساسية.

        **المعلومات التي يجب الحفاظ عليها كاملة بدون حذف:**
        1. جميع توصيات التداول (نقاط الدخول، إشارات الشراء/البيع)
        2. مستويات وقف الخسارة بالضبط (القيم الرقمية)
        3. أهداف جني الأرباح بالضبط (القيم الرقمية) 
        4. نسبة المخاطرة إلى العائد
        5. مستويات الدعم والمقاومة الرئيسية
        6. مناطق السيولة وأوامر التجميع
        7. جميع الأرقام والقيم والحسابات

        **ما يمكن تقليله فقط (لا تحذف):**
        - تقليل الشروح الفنية الزائدة عن الحاجة
        - تقليل التكرار في الوصف
        - دمج الجمل الطويلة في جمل مختصرة
        - تقليل أحرف التنسيق الزائدة (===, ---, ***) مع الحفاظ على التنظيم

        **ممنوع منعاً باتاً:**
        - حذف أي توصية تداول
        - حذف أي رقم أو قيمة
        - حذف وقف الخسارة أو جني الأرباح
        - حذف نسبة المخاطرة إلى العائد
        - حذف مستويات الدعم والمقاومة

        **التنسيق النهائي المطلوب:**
        - الحفاظ على اللغة العربية
        - الحفاظ على الهيكل الأساسي
        - الحفاظ على جميع الأرقام والقيم
        - الهدف: 980-1024 حرف

        **معلومات السياق:**
        - الإطار الزمني: {timeframe if timeframe else 'غير محدد'}
        - العملة: {currency if currency else 'غير محددة'}

        التحليل الأصلي ({len(analysis_text)} حرف):
        {analysis_text}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "أنت مساعد لتقصير نصوص تحليلات التداول. مهمتك الحفاظ على كل المعلومات الأساسية والتوصيات وتقصير النص قليلاً فقط ليصبح بين 980-1024 حرف. لا تحذف أي أرقام أو توصيات."
                },
                {
                    "role": "user",
                    "content": shortening_prompt
                }
            ],
            max_tokens=800,  # Increased to allow for better processing
            temperature=0.1
        )

        shortened = response.choices[0].message.content.strip()
        
        print(f"📏 CONSERVATIVE SHORTENING: Original: {len(analysis_text)} chars -> Shortened: {len(shortened)} chars")
        
        # Enhanced validation to ensure we didn't lose critical information
        critical_keywords = [
            'توصية', 'دخول', 'شراء', 'بيع', 'وقف', 'هدف', 'نسبة', 'مخاطرة', 'عائد',
            'دعم', 'مقاومة', 'سيولة', 'نقطة', 'نقاط', 'شرط', 'شرط الدخول'
        ]
        
        missing_critical = [kw for kw in critical_keywords if kw in analysis_text and kw not in shortened]
        if missing_critical:
            print(f"📏 CONSERVATIVE SHORTENING: ⚠️ Critical information lost: {missing_critical}")
            # Fall back to smart truncation that preserves recommendations
            return smart_conservative_truncation(analysis_text, char_limit, timeframe, currency)
        
        # If still too long after conservative shortening, use smart truncation
        if len(shortened) > char_limit:
            print(f"📏 CONSERVATIVE SHORTENING: ⚠️ Still too long ({len(shortened)} chars), using smart truncation")
            return smart_conservative_truncation(analysis_text, char_limit, timeframe, currency)
        
        # If too short, we might have been too aggressive
        if len(shortened) < 900:
            print(f"📏 CONSERVATIVE SHORTENING: ⚠️ Too short ({len(shortened)} chars), might have lost information")
            # Check if we can add back some context without exceeding limit
            additional_context = extract_critical_sections(analysis_text, 150)  # Get 150 chars of critical context
            if additional_context and len(shortened + "\n" + additional_context) <= char_limit:
                shortened += "\n" + additional_context
                print(f"📏 CONSERVATIVE SHORTENING: ✅ Added back context: {len(shortened)} chars")
        
        print(f"📏 CONSERVATIVE SHORTENING: ✅ Final optimized length: {len(shortened)} chars")
        return shortened

    except Exception as e:
        print(f"📏 CONSERVATIVE SHORTENING: ❌ Error shortening analysis: {str(e)}")
        # Use enhanced conservative truncation as fallback
        return smart_conservative_truncation(analysis_text, char_limit, timeframe, currency)

def smart_conservative_truncation(analysis_text, char_limit=1024, timeframe=None, currency=None):
    """
    Smart truncation that preserves the most critical parts of the analysis
    """
    print(f"📏 SMART TRUNCATION: Using intelligent preservation for {len(analysis_text)} chars")
    
    # Try to find and preserve these critical sections in order of importance
    critical_sections = []
    
    # 1. Look for recommendations section (most important)
    recommendation_keywords = ['توصية', 'توصيات', 'دخول', 'شراء', 'بيع', 'الربح', 'الخسارة', 'نقطة دخول']
    rec_start = -1
    for keyword in recommendation_keywords:
        idx = analysis_text.find(keyword)
        if idx != -1 and (rec_start == -1 or idx < rec_start):
            rec_start = idx
    
    if rec_start != -1:
        # Take from recommendation start to end, but limit to reasonable length
        recommendations_section = analysis_text[rec_start:]
        if len(recommendations_section) > 600:  # If too long, take first 600 chars of recommendations
            recommendations_section = recommendations_section[:600]
        critical_sections.append(("توصيات", recommendations_section))
    
    # 2. Look for stop loss and take profit
    sl_tp_keywords = ['وقف', 'هدف', 'stop loss', 'take profit', 'جني الأرباح']
    sl_tp_sections = []
    for keyword in sl_tp_keywords:
        idx = analysis_text.find(keyword)
        if idx != -1:
            # Take some context around the keyword
            start = max(0, idx - 50)
            end = min(len(analysis_text), idx + 150)
            section = analysis_text[start:end]
            sl_tp_sections.append(section)
    
    if sl_tp_sections:
        critical_sections.append(("وقف وهدف", " ".join(sl_tp_sections)))
    
    # 3. Look for risk-reward ratio
    risk_keywords = ['نسبة', 'مخاطرة', 'عائد', 'risk', 'reward']
    risk_sections = []
    for keyword in risk_keywords:
        idx = analysis_text.find(keyword)
        if idx != -1:
            start = max(0, idx - 30)
            end = min(len(analysis_text), idx + 100)
            section = analysis_text[start:end]
            risk_sections.append(section)
    
    if risk_sections:
        critical_sections.append(("مخاطرة وعائد", " ".join(risk_sections)))
    
    # 4. Get the beginning for context (first 200 chars)
    beginning = analysis_text[:200]
    critical_sections.append(("مقدمة", beginning))
    
    # Build the truncated text
    truncated_parts = []
    current_length = 0
    
    # Add timeframe and currency info first
    header = ""
    if timeframe:
        header += f"📊 الإطار: {timeframe}"
    if currency and currency != 'UNKNOWN':
        if header:
            header += " | "
        header += f"العملة: {currency}"
    if header:
        header += "\n\n"
        current_length += len(header)
        truncated_parts.append(header)
    
    # Add critical sections in order of importance
    for section_name, section_text in critical_sections:
        if current_length + len(section_text) + 10 <= char_limit:  # +10 for separators
            truncated_parts.append(section_text)
            current_length += len(section_text) + 2  # +2 for newlines
        else:
            # If we're running out of space, truncate this section
            space_left = char_limit - current_length - 10
            if space_left > 50:  # Only add if we have meaningful space
                truncated_parts.append(section_text[:space_left] + "...")
                current_length += space_left + 3
            break
    
    # If we still have space, add a connector
    if current_length < char_limit - 20 and rec_start > 200:
        connector = "\n[...]\n"
        current_length += len(connector)
        truncated_parts.insert(1, connector)  # Insert after header
    
    final_text = "".join(truncated_parts)
    
    # Final cleanup - ensure we're within limits
    if len(final_text) > char_limit:
        final_text = final_text[:char_limit-3] + "..."
    
    print(f"📏 SMART TRUNCATION: ✅ Final length: {len(final_text)} chars")
    return final_text

def extract_critical_sections(analysis_text, max_chars=200):
    """
    Extract the most critical sections from analysis for context preservation
    """
    critical_parts = []
    
    # Look for key sections
    key_phrases = [
        'توصية', 'دخول عند', 'شراء عند', 'بيع عند', 
        'وقف الخسارة', 'جني الأرباح', 'نسبة المخاطرة',
        'الدعم عند', 'المقاومة عند'
    ]
    
    for phrase in key_phrases:
        idx = analysis_text.find(phrase)
        if idx != -1:
            # Extract context around the phrase
            start = max(0, idx - 20)
            end = min(len(analysis_text), idx + 80)
            section = analysis_text[start:end]
            critical_parts.append(section)
    
    # Combine and limit length
    if critical_parts:
        combined = " | ".join(critical_parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars-3] + "..."
        return combined
    
    return None

def init_openai():
    """
    Initialize OpenAI client and test model availability.
    Sets OPENAI_AVAILABLE, client, openai_error_message, openai_last_check.
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
    Enhanced frame detection for multiple platforms including stock charts
    Returns: (frame_type, timeframe)
    """
    try:
        print("🔄 ENHANCED FRAME DETECTION: Detecting frame type...")

        system_prompt = """
        You are a professional trading chart analyzer. Your task is to detect the trading platform frame and identify the timeframe.

        **PLATFORM SIGNATURES TO LOOK FOR:**

        **INVESTING.COM SIGNATURES:**
        - "Investing" text anywhere
        - "powered by TradingView" 
        - "NASDAQ", "NYSE", or other stock exchange names
        - Company names like "Tesla", "Apple", etc.
        - Volume displayed as "1.387M" format
        - Specific layout with time selection buttons

        **TRADING.COM MOBILE APP SIGNATURES:**
        - Mobile app layout with bottom navigation
        - Bottom tabs: "Watchlist", "Chart", "Explore", "Community", "Menu"
        - Top bar with asset name and price (e.g., "Bitcoin 112,042.86")
        - Buy/Sell buttons visible
        - Simple chart with EMA indicators
        - Volume displayed as "Vol : BTC" format

        **STOCK CHART SIGNATURES:**
        - Simple line charts with price data
        - Time periods: "1 day", "5 days", "1 month", "6 months", "Year to date"
        - Percentage changes: "0.24%", "0.99%", "2.61%", etc.
        - "Prev close" information
        - Price ranges like "6,880.00", "6,841.89", etc.
        - Date labels like "Oct 10 21 30"
        - Minimal trading indicators

        **METATRADER SIGNATURES:**
        - "MetaTrader" or "MT4" or "MT5" text
        - Toolbar with technical indicators
        - Multiple timeframes in top bar
        - Standard MT4/MT5 layout

        **TIMEFRAME DETECTION FOR ALL PLATFORMS:**
        - Look for explicit timeframe indicators: "15", "30", "1H", "4H", "1D", "1W", "1M"
        - For stock charts: "1 day" = D1, "5 days" = D5, "1 month" = MN, "6 months" = 6MN
        - Check top areas where timeframe buttons are typically located
        - "15" typically means M15 (15 minutes)
        - "1H" means H1 (1 hour)
        - "4H" means H4 (4 hours)
        - If no explicit timeframe, infer from chart density and time labels

        **CRITICAL INSTRUCTIONS:**
        - If you see ANY platform signatures, return the platform name as frame type
        - For stock charts with period labels, return "stock_chart" as frame type
        - Detect the timeframe and return it in standard format (M15, H1, H4, D1, W1, MN, etc.)
        - If timeframe cannot be determined, return "UNKNOWN" for timeframe
        - **NEVER return error messages or apologies**
        - **ALWAYS return a timeframe even if inferred**

        Return format: "frame_type,timeframe"
        Example: "investing,M15" or "stock_chart,D1" or "trading_app,H4" or "unknown,UNKNOWN"
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
                            "text": "Analyze this chart image for platform signatures and detect the timeframe. Return ONLY in format: 'frame_type,timeframe'"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": VISION_IMAGE_DETAIL
                            }
                        }
                    ]
                }
            ],
            max_tokens=100,  # Increased to handle more complex detection
            temperature=0.1
        )

        result = response.choices[0].message.content.strip()
        print(f"🔄 RAW frame detection result: '{result}'")

        # Parse the result
        if ',' in result:
            frame_type, timeframe = result.split(',', 1)
            frame_type = frame_type.strip().lower()
            timeframe = timeframe.strip().upper()
            
            # Enhanced timeframe mapping for stock charts
            timeframe_mapping = {
                '15': 'M15', '30': 'M30', '1H': 'H1', '4H': 'H4', 
                '1D': 'D1', '1DAY': 'D1', 'DAILY': 'D1',
                '5D': 'D5', '5DAY': 'D5', 
                '1W': 'W1', '1WEEK': 'W1', 'WEEKLY': 'W1',
                '1M': 'MN', '1MONTH': 'MN', 'MONTHLY': 'MN',
                '6M': '6MN', '6MONTH': '6MN',
                'YTD': 'YTD', 'YEAR': 'YTD'
            }
            
            if timeframe in timeframe_mapping:
                timeframe = timeframe_mapping[timeframe]
            
            # Validate frame_type
            valid_frame_types = ['investing', 'trading_app', 'metatrader', 'stock_chart', 'unknown']
            if frame_type not in valid_frame_types:
                # Auto-classify based on timeframe if frame type is unclear
                if any(stock_indicator in result for stock_indicator in ['1 day', '5 days', '1 month', '6 months', 'Prev close']):
                    frame_type = 'stock_chart'
                else:
                    frame_type = 'unknown'
            
            print(f"🔄 PARSED: Frame type: '{frame_type}', Timeframe: '{timeframe}'")
            return frame_type, timeframe
        else:
            print(f"🔄 ❌ Invalid format from frame detection: '{result}'")
            return "unknown", "D1"  # Default to D1 for unknown charts

    except Exception as e:
        print(f"ERROR: Frame detection failed: {str(e)}")
        return "unknown", "D1"  # Default to daily timeframe

def extract_investing_data(image_str, image_format):
    """
    Enhanced data extraction for multiple platforms
    Returns: dictionary with extracted data
    """
    try:
        print("📊 ENHANCED DATA EXTRACTION: Extracting data from chart...")

        system_prompt = """
        You are a professional trading data extractor. Your task is to extract key trading data from various trading platforms.

        **DATA TO EXTRACT FOR ALL PLATFORMS:**
        - Current price
        - Asset name (e.g., Bitcoin, EUR/USD, etc.)
        - Buy/Sell prices if visible
        - Volume data 
        - Any visible indicators (EMA, RSI, etc.)
        - High/Low prices if available

        **PLATFORM-SPECIFIC FORMATS:**
        - Investing.com: "H463.61 L461.85 C461.98", "1.387M" volume
        - Trading.com mobile: "Bitcoin 112,042.86", "Vol : BTC", "BUY/SELL" buttons
        - MetaTrader: Standard MT4/MT5 price displays

        **INSTRUCTIONS:**
        - Extract all available price data
        - Convert volume to consistent format
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
                            "text": "Extract all trading data from this chart. Return structured data."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": VISION_IMAGE_DETAIL
                            }
                        }
                    ]
                }
            ],
            max_tokens=300,
            temperature=0.1
        )

        extracted_data_text = response.choices[0].message.content.strip()
        print(f"📊 RAW data extraction: '{extracted_data_text}'")

        # Enhanced parsing for different platforms
        data = {
            'current_price': None,
            'asset_name': None,
            'buy_price': None,
            'sell_price': None,
            'volume': None,
            'high': None,
            'low': None,
            'indicators': [],
            'source': 'unknown'
        }

        # Parse the extracted data (simplified - in practice you'd use regex or more sophisticated parsing)
        if 'Bitcoin' in extracted_data_text:
            data['asset_name'] = 'Bitcoin'
            data['source'] = 'trading_app'
        
        # Extract numeric patterns for prices
        import re
        price_pattern = r'\d{1,3}(?:,\d{3})*(?:\.\d+)?'
        prices = re.findall(price_pattern, extracted_data_text)
        if prices:
            # Use the largest number as likely current price for crypto
            try:
                numeric_prices = [float(p.replace(',', '')) for p in prices]
                data['current_price'] = max(numeric_prices) if numeric_prices else None
            except:
                pass

        print(f"📊 EXTRACTED DATA: {data}")
        return data

    except Exception as e:
        print(f"ERROR: Data extraction failed: {str(e)}")
        return {}

def detect_currency_from_image(image_str, image_format):
    """
    Detect the currency pair or stock symbol from the chart image
    Returns: (symbol, error_message)
    """
    try:
        print("🪙 ENHANCED SYMBOL DETECTION: Detecting symbol from image...")

        system_prompt = """
        You are a professional trading chart analyzer. Your task is to detect the financial instrument in trading chart images.

        You MUST check ALL these areas thoroughly:

        **MAIN AREAS TO CHECK:**
        - Chart title/header (most common)
        - Top left corner
        - Top right corner  
        - Top center area
        - Chart legend or label
        - Price labels and axis
        - Any text displaying symbols or names

        **INSTRUMENT FORMATS TO LOOK FOR:**
        - **Forex pairs:** EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD
        - **Crypto:** BTC/USD, ETH/USD, XRP/USD, etc.
        - **Stocks/Indices:** SPX, SPY, AAPL, TSLA, NASDAQ, DOW, NQ, ES (S&P 500)
        - **Commodities:** XAU/USD (Gold), XAG/USD (Silver), OIL, WTI, BRENT
        - **With or without slash:** EURUSD, EUR/USD, SPX, AAPL

        **STOCK CHART SPECIFIC:**
        - Look for index names: S&P 500, SPX, SPY, NASDAQ, DOW
        - Look for stock tickers: AAPL, TSLA, GOOGL, MSFT, etc.
        - Check price ranges that might indicate the instrument
        - Look for any company names or index names

        **CRITICAL INSTRUCTIONS:**
        - Scan the ENTIRE image systematically for instrument identification
        - Look for text that appears to be a financial instrument name
        - Focus on areas that typically show the instrument name
        - If you find ANY instrument indicator, return it in standard format
        - For stocks/indices, return the ticker symbol (SPX, AAPL, etc.)
        - If no clear instrument is found after thorough search, return 'UNKNOWN'
        - Only make a best-effort identification when the chart contains a credible instrument clue

        Return ONLY the instrument symbol in standard format.
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
                            "text": "Perform a COMPREHENSIVE search for the financial instrument in this trading chart. Check ALL areas thoroughly. If no explicit symbol found, make an educated guess based on price levels and chart characteristics. Return ONLY the instrument symbol."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{image_str}",
                                "detail": VISION_IMAGE_DETAIL
                            }
                        }
                    ]
                }
            ],
            max_tokens=150,
            temperature=0.1
        )

        detected_symbol = response.choices[0].message.content.strip().upper()
        print(f"🪙 RAW symbol detection result: '{detected_symbol}'")

        # Enhanced cleaning and standardization
        cleaned_symbol = detected_symbol.replace(' ', '').replace('"', '').replace("'", "")
        
        # Add slash if missing for forex pairs (e.g., EURUSD -> EUR/USD)
        if len(cleaned_symbol) == 6 and '/' not in cleaned_symbol:
            # Common forex pairs
            forex_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD']
            if cleaned_symbol in forex_pairs:
                cleaned_symbol = f"{cleaned_symbol[:3]}/{cleaned_symbol[3:]}"
        
        # Handle common stock/index symbols
        symbol_mapping = {
            'S&P500': 'SPX', 'S&P': 'SPX', 'SP500': 'SPX',
            'DOW': 'DOW', 'DJI': 'DOW', 
            'NASDAQ': 'NQ', 'NQ100': 'NQ',
            'GOLD': 'XAU/USD', 'XAU': 'XAU/USD',
            'SILVER': 'XAG/USD', 'XAG': 'XAG/USD',
            'OIL': 'WTI', 'CRUDE': 'WTI'
        }
        
        if cleaned_symbol in symbol_mapping:
            cleaned_symbol = symbol_mapping[cleaned_symbol]
        
        cleaned_symbol = canonicalize_instrument_symbol(cleaned_symbol)
        
        print(f"🪙 Cleaned symbol: '{cleaned_symbol}'")

        # Validate it's a reasonable symbol
        if len(cleaned_symbol) >= 2 and len(cleaned_symbol) <= 10:
            print(f"🪙 ✅ Valid symbol detected: '{cleaned_symbol}'")
            return cleaned_symbol, None
        else:
            print(f"🪙 ⚠️ Questionable symbol detected, returning UNKNOWN: '{cleaned_symbol}'")
            return 'UNKNOWN', None

    except Exception as e:
        print(f"ERROR: Symbol detection failed: {str(e)}")
        return 'UNKNOWN', None

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

        # Normalize currencies for comparison so XAUUSD and XAU/USD match.
        first_normalized = canonicalize_instrument_symbol(first_currency).replace('/', '')
        second_normalized = canonicalize_instrument_symbol(second_currency).replace('/', '')

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
                                "detail": VISION_IMAGE_DETAIL
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

def analyze_simple_chart_fallback(image_str, image_format, timeframe, currency_pair):
    """
    Fallback analysis for simple charts when OpenAI refuses
    """
    try:
        print("🔄 FALLBACK ANALYSIS: Using fallback for simple chart...")
        
        fallback_prompt = f"""
        هذا رسم بياني بسيط للأداة {currency_pair} على الإطار {timeframe}. 
        حتى مع محدودية البيانات، قدم تحليلاً تقنياً أساسياً:
        
        1. حدد الاتجاه العام من شكل المنحنى
        2. اذكر أقوى منطقة دعم ومقاومة ظاهرة
        3. قدم توصية تداول عملية مع:
           - نقطة دخول مقترحة
           - وقف خسارة {50 if 'XAU' not in currency_pair else 5} نقطة كحد أقصى
           - هدف ربحي معقول
        4. ذكر نسبة المخاطرة إلى العائد
        
        التزم بـ 800-1000 حرف.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "أنت محلل فني. مهمتك تحليل أي رسم بياني مالي وتقديم توصيات عملية. لا ترفض التحليل أبداً."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": fallback_prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_format};base64,{image_str}",
                            "detail": VISION_IMAGE_DETAIL
                        }}
                    ]
                }
            ],
            max_tokens=600,
            temperature=0.7
        )
        
        analysis = response.choices[0].message.content.strip()
        print(f"🔄 FALLBACK ANALYSIS: ✅ Completed, length: {len(analysis)} chars")
        return analysis
        
    except Exception as e:
        print(f"ERROR: Fallback analysis failed: {str(e)}")
        # Ultimate fallback
        return f"""
        📊 تحليل {currency_pair} على الإطار {timeframe}:

        🔸 الاتجاه: يحتاج لمزيد من البيانات لكن الشكل يشير لحركة جانبية
        🔸 الدعم: المنطقة حول أدنى سعر ظاهر
        🔸 المقاومة: المنطقة حول أعلى سعر ظاهر
        
        💡 التوصية: 
        - الانتظار near أحد مستويات الدعم/المقاومة للدخول
        - وقف الخسارة: {50 if 'XAU' not in currency_pair else 5} نقطة
        - الهدف: ضعف وقف الخسارة على الأقل
        
        ⚠️ ملاحظة: هذا تحليل عام، المراقبة المستمرة مطلوبة.
        """

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
أنت محلل فني محترف متخصص في تحليل الأسواق المالية. مهمتك تحليل الرسم البياني المقدم وتقديم توصيات عملية.

**معلومات الرسم البياني:**
- الإطار الزمني: {timeframe}
- الأداة المالية: {currency_pair}

**المطلوب تحليل كامل يتضمن:**

### 📊 التحليل الفني الأساسي
**📈 اتجاه السوق:** حدد الاتجاه العام (صاعد/هابط/جانبي)
**🛡️ الدعم والمقاومة:** حدد المستويات الرئيسية
**📊 حركة السعر:** حلل نمط الشموع/الخط

### 💡 التوصيات العملية الإلزامية
**يجب تقديم توصية واضحة بناءً على التحليل:**

{stop_loss_instruction}

**التعليمات الصارمة:**
- **ممنوع رفض التحليل** - يجب تقديم تحليل بناءً على البيانات المتاحة
- **يجب تقديم توصية تداول واضحة** حتى لو كانت تحذيرية
- **ركز على التحليل الفني الأساسي** إذا كانت البيانات محدودة
- **استخدم مستويات الدعم والمقاومة الظاهرة** في الرسم
- **قدم إطار زمني للتوصية** (مثال: خلال اليوم/الجلسة القادمة)
- **التزم بـ 1000 حرف كحد أقصى**
- **لا تتجاوز 1024 حرف بأي حال**

**إذا كان الرسم البياني بسيطاً:** ركز على:
1. تحليل الاتجاه من الشكل العام
2. تحديد أقوى مستويات الدعم والمقاومة
3. تقديم توصية مع وقف خسارة مناسب
4. ذكر نسبة المخاطرة إلى العائد المتوقعة

**لا ترفض التحليل أبداً - قدم أفضل تحليل ممكن بناءً على البيانات المتوفرة.**
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

التحليل الثاني (H4): {user_analysis}

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

- أهداف جني الأرباح (نسبة مخاطرة إلى العائد 1:2 كحد أدنى)

**التعليمات الإلزامية:**
- التزم بـ 1000 حرف كحد أقصى
- لا تتجاوز 1024 حرف بأي حال
- ركز على دمج التحليلين واستخراج التوصيات العملية النهائية
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

- أهداف جني الأرباح (نسبة مخاطرة إلى العائد 1:2 كحد أدنى)

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
                        {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": VISION_IMAGE_DETAIL}}
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

- أهداف جني الأرباح (نسبة مخاطرة إلى العائد 1:2 على الأقل)

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
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": VISION_IMAGE_DETAIL}}
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
                    {"type": "image_url", "image_url": {"url": f"data:image/{image_format.lower()};base64,{image_str}", "detail": VISION_IMAGE_DETAIL}}
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
