import base64
import requests
from io import BytesIO
from PIL import Image
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from openai_utils import analyze_with_openai, init_openai, OPENAI_AVAILABLE, openai_error_message, openai_last_check, init_openai as _init_openai
# analysis_sessions lives here
api_bp = Blueprint('api', __name__)

analysis_sessions = {}

@api_bp.route('/')
def home():
    status = "✅" if OPENAI_AVAILABLE else "❌"
    return f"XFLEXAI Server is running {status} - OpenAI: {'Available' if OPENAI_AVAILABLE else openai_error_message}"

@api_bp.route('/analyze', methods=['POST'])
def analyze():
    """Main endpoint supporting different analysis actions (chart_analysis, add_timeframe, user_analysis, new_analysis)"""
    try:
        if not request.is_json:
            return jsonify({
                "success": False,
                "message": "نوع المحتوى غير مدعوم",
                "analysis": "يجب أن يكون الطلب بتنسيق JSON"
            }), 415

        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "message": "لم يتم إرسال بيانات",
                "analysis": "لم يتم إرسال بيانات للتحليل"
            }), 400

        user_id = data.get('user_id', 'default_user')
        action_type = data.get('action_type', 'chart_analysis')  # chart_analysis, add_timeframe, user_analysis
        image_url = data.get('image_url')
        user_analysis_text = data.get('user_analysis')
        timeframe = data.get('timeframe', 'M15')

        if not image_url and not user_analysis_text:
            return jsonify({
                "success": False,
                "message": "بيانات غير كافية",
                "analysis": "يجب تقديم صورة أو تحليل نصي"
            }), 400

        # initialize session
        if user_id not in analysis_sessions:
            analysis_sessions[user_id] = {
                'user_id': user_id,
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'created_at': datetime.now(),
                'status': 'ready',
                'conversation_history': []
            }

        session_data = analysis_sessions[user_id]

        # load image if present
        image_str = None
        image_format = None
        if image_url:
            try:
                response = requests.get(image_url, timeout=10)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    if img.format in ['PNG', 'JPEG', 'JPG']:
                        buffered = BytesIO()
                        img_format = img.format if img.format else 'JPEG'
                        img.save(buffered, format=img_format)
                        image_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            except Exception as e:
                print(f"Error loading image: {e}")

        if not OPENAI_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "خدمة الذكاء الاصطناعي غير متوفرة",
                "analysis": openai_error_message
            }), 503

        # handle actions
        if action_type == 'chart_analysis':
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "تعذر تحميل الصورة المطلوبة"
                }), 400

            analysis = analyze_with_openai(image_str, img_format, timeframe)
            session_data['first_analysis'] = analysis
            session_data['first_timeframe'] = timeframe
            session_data['status'] = 'first_analysis_done'

            session_data['conversation_history'].append({
                'type': 'analysis',
                'timeframe': timeframe,
                'content': analysis,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": f"✅ تم تحليل {timeframe} بنجاح",
                "analysis": analysis,
                "user_id": user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "add_timeframe", "label": "➕ إضافة إطار زمني آخر"},
                    {"action": "user_analysis", "label": "📝 إضافة تحليلي الشخصي"}
                ]
            }), 200

        elif action_type == 'add_timeframe':
            if not image_str:
                return jsonify({
                    "success": False,
                    "message": "صورة غير صالحة",
                    "analysis": "تعذر تحميل الصورة المطلوبة"
                }), 400

            if session_data['status'] != 'first_analysis_done':
                return jsonify({
                    "success": False,
                    "message": "خطأ في التسلسل",
                    "analysis": "يجب تحليل الإطار الأول قبل إضافة الثاني"
                }), 400

            if session_data['first_timeframe'] == 'M15':
                new_timeframe = 'H4'
            else:
                new_timeframe = 'M15'

            analysis = analyze_with_openai(image_str, img_format, new_timeframe, session_data['first_analysis'])
            session_data['second_analysis'] = analysis
            session_data['second_timeframe'] = new_timeframe
            session_data['status'] = 'both_analyses_done'

            final_analysis = analyze_with_openai(
                None, None, "H4",
                f"{session_data['first_timeframe']}: {session_data['first_analysis']}",
                None, "chart_analysis"
            )

            session_data['conversation_history'].append({
                'type': 'analysis',
                'timeframe': new_timeframe,
                'content': analysis,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": "✅ تم التحليل الشامل بنجاح",
                "analysis": final_analysis,
                "user_id": user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "user_analysis", "label": "📝 إضافة تحليلي الشخصي للحصول على تقييم"}
                ]
            }), 200

        elif action_type == 'user_analysis':
            if not user_analysis_text:
                return jsonify({
                    "success": False,
                    "message": "تحليل نصي مطلوب",
                    "analysis": "يرجى تقديم تحليلك النصي"
                }), 400

            feedback = analyze_with_openai(
                image_str, img_format if image_str else None,
                None, None, user_analysis_text, "user_analysis_feedback"
            )

            session_data['user_analysis'] = user_analysis_text
            session_data['status'] = 'user_analysis_reviewed'

            session_data['conversation_history'].append({
                'type': 'user_analysis',
                'content': user_analysis_text,
                'feedback': feedback,
                'timestamp': datetime.now()
            })

            return jsonify({
                "success": True,
                "message": "✅ تم تقييم تحليلك بنجاح",
                "analysis": feedback,
                "user_id": user_id,
                "status": session_data['status'],
                "next_actions": [
                    {"action": "new_analysis", "label": "🔄 بدء تحليل جديد"}
                ]
            }), 200

        elif action_type == 'new_analysis':
            analysis_sessions[user_id] = {
                'user_id': user_id,
                'first_analysis': None,
                'second_analysis': None,
                'first_timeframe': None,
                'second_timeframe': None,
                'user_analysis': None,
                'created_at': datetime.now(),
                'status': 'ready',
                'conversation_history': session_data.get('conversation_history', [])
            }

            return jsonify({
                "success": True,
                "message": "🔄 تم بدء جلسة تحليل جديدة",
                "analysis": "يمكنك الآن إرسال صورة الرسم البياني للتحليل",
                "user_id": user_id,
                "status": 'ready',
                "next_actions": [
                    {"action": "chart_analysis", "label": "📊 تحليل رسم بياني", "requires_image": True}
                ]
            }), 200

        else:
            return jsonify({
                "success": False,
                "message": "نوع إجراء غير معروف",
                "analysis": f"نوع الإجراء {action_type} غير مدعوم"
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"خطأ أثناء المعالجة: {str(e)}",
            "analysis": f"فشل في التحليل: {str(e)}"
        }), 400

@api_bp.route('/sendpulse-analyze', methods=['POST'])
def sendpulse_analyze():
    data = request.get_json()
    if data:
        data['action_type'] = 'chart_analysis'
        if 'timeframe' not in data:
            data['timeframe'] = 'M15'
    return analyze()

@api_bp.route('/multi-timeframe-analyze', methods=['POST'])
def multi_timeframe_analyze():
    return sendpulse_analyze()

@api_bp.route('/user-analysis', methods=['POST'])
def user_analysis():
    data = request.get_json()
    if data:
        data['action_type'] = 'user_analysis'
    return analyze()

@api_bp.route('/status')
def status():
    # refresh OpenAI status periodically
    if time.time() - openai_last_check > 300:
        try:
            _init_openai()
        except Exception:
            pass

    return jsonify({
        "server": "running",
        "openai_available": OPENAI_AVAILABLE,
        "openai_error": openai_error_message,
        "active_sessions": len(analysis_sessions),
        "timestamp": time.time()
    })

@api_bp.route('/session-info/<user_id>')
def session_info(user_id):
    if user_id in analysis_sessions:
        session_data = analysis_sessions[user_id].copy()
        if 'conversation_history' in session_data:
            session_data['conversation_count'] = len(session_data['conversation_history'])
            del session_data['conversation_history']
        return jsonify({"success": True, "session": session_data})
    else:
        return jsonify({"success": False, "message": "الجلسة غير موجودة"})

@api_bp.route('/clear-sessions')
def clear_sessions():
    global analysis_sessions
    count = len(analysis_sessions)
    analysis_sessions = {}
    return jsonify({
        "message": f"تم مسح {count} جلسة",
        "status": "sessions_cleared"
    })
