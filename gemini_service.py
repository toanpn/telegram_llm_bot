import asyncio
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime

import google.generativeai as genai
from loguru import logger

from config import config

class GeminiService:
    """Service for interacting with Google Gemini AI."""
    
    def __init__(self):
        self.model = None
        self._initialize_gemini()
    
    def _initialize_gemini(self):
        """Initialize the Gemini AI model."""
        try:
            genai.configure(api_key=config.google_api_key)
            self.model = genai.GenerativeModel(config.gemini_model)
            logger.info("Gemini AI service initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Gemini AI: {e}")
            raise
    
    async def analyze_intent(self, message: str, context_messages: List[Dict], 
                           temperature: float = 0.7, tone: str = "friendly") -> Dict[str, Any]:
        """Analyze user message intent using AI."""
        try:
            # Build context string
            context_str = self._build_context_string(context_messages)
            
            # Create intent analysis prompt
            prompt = f"""
Analyze this message to understand the user's intent. Based on the context and message, determine what the user wants to do.

Context from recent messages:
{context_str}

Current message: "{message}"

Please analyze and respond with a JSON object containing:
1. "intent": one of ["save_info", "retrieve_info", "summarize", "conversation"]
2. If intent is "save_info":
   - "key": the type of information being saved (e.g., "facebook_link", "bank_account", "phone_number")
   - "value": the actual information to save
3. If intent is "retrieve_info":
   - "key": the type of information being requested
   - "target_username": the username of the person whose info is being requested (without @)
4. If intent is "summarize":
   - "message_count": number of messages to summarize (default 20)
5. If intent is "conversation":
   - "response_type": "general" (for normal conversation)

Examples:
- "save my phone number 123-456-7890" → {{"intent": "save_info", "key": "phone_number", "value": "123-456-7890"}}
- "what's @john's email?" → {{"intent": "retrieve_info", "key": "email", "target_username": "john"}}
- "summarize the last 10 messages" → {{"intent": "summarize", "message_count": 10}}
- "how are you?" → {{"intent": "conversation", "response_type": "general"}}

Response format: JSON only, no additional text.
"""
            
            # Generate response
            response = await self._generate_response(prompt, temperature=0.3)  # Lower temperature for intent analysis
            
            # Parse JSON response
            try:
                # Clean up response - remove code blocks if present
                clean_response = response.strip()
                if clean_response.startswith("```json"):
                    clean_response = clean_response[7:]  # Remove ```json
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]  # Remove ```
                clean_response = clean_response.strip()
                
                intent_data = json.loads(clean_response)
                return intent_data
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse intent JSON: {response}")
                return {"intent": "conversation", "response_type": "general"}
                
        except Exception as e:
            logger.error(f"Error analyzing intent: {e}")
            return {"intent": "conversation", "response_type": "general"}
    
    async def generate_response(self, message: str, context_messages: List[Dict], 
                              temperature: float = 0.7, tone: str = "friendly") -> str:
        """Generate a conversational response."""
        try:
            # Build context string
            context_str = self._build_context_string(context_messages)
            
            # Map English tone to Vietnamese descriptions with detailed behaviors
            tone_mapping = {
                "friendly": "thân thiện và gần gũi. Hay dùng \"bạn\", \"mình\". Ấm áp, dễ gần.",
                "professional": "chuyên nghiệp và lịch sự. Dùng \"anh/chị\", \"quý khách\". Trang trọng nhưng thân thiện.",
                "humorous": "hài hước và vui vẻ. Hay đùa, dùng meme, emoji nhiều. Tạo không khí vui vẻ.",
                "serious": "nghiêm túc và trang trọng. Ít đùa, tập trung vào vấn đề. Thẳng thắn, rõ ràng.",
                "flattering": "nịnh nọt và khen ngợi. Luôn gọi thành viên là 'ông chủ', 'bà chủ', 'ngài'. Tự xưng là 'em nhỏ', 'tôi khiêm tốn'. Hay khen ngợi, tâng bốc một cách hài hước.",
                "casual": "thoải mái và bình dân. Dùng 'mày/tao', 'bro', 'chị em'. Không câu nệ, tự nhiên.",
                "formal": "hiền triết và sâu sắc. Hay dùng thành ngữ, tục ngữ, câu nói triết lý. Phong cách văn hoa, uyên bác."
            }
            
            vietnamese_tone = tone_mapping.get(tone, "thân thiện và gần gũi")
            
            # Create conversation prompt - forcing Vietnamese response
            prompt = f"""
Bạn là Huấn, một trợ lý AI hữu ích trong nhóm chat Telegram. Mọi người thường gọi bạn là "thầy Huấn". 
Tính cách của bạn nên {vietnamese_tone}.

QUAN TRỌNG: Bạn PHẢI trả lời HOÀN TOÀN bằng tiếng Việt. Không được sử dụng tiếng Anh hoặc ngôn ngữ khác.

Ngữ cảnh từ các tin nhắn gần đây:
{context_str}

Tin nhắn hiện tại: "{message}"

Hãy trả lời một cách tự nhiên và hữu ích bằng tiếng Việt với tư cách là thầy Huấn. 
Giữ câu trả lời ngắn gọn nhưng đầy đủ thông tin.
Duy trì giọng điệu {vietnamese_tone} trong suốt câu trả lời của bạn.
"""
            
            # Generate response
            response = await self._generate_response(prompt, temperature)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Xin lỗi, tôi đang gặp khó khăn trong việc xử lý tin nhắn của bạn. Vui lòng thử lại."
    
    async def summarize_conversation(self, messages: List[Dict]) -> str:
        """Summarize a conversation from message history."""
        try:
            # Build conversation string
            conversation_str = self._build_conversation_string(messages)
            
            # Create summarization prompt - forcing Vietnamese response
            prompt = f"""
Hãy cung cấp một tóm tắt ngắn gọn về cuộc trò chuyện này bằng tiếng Việt. 
Tập trung vào các chủ đề chính được thảo luận, các quyết định quan trọng và thông tin quan trọng được chia sẻ.

QUAN TRỌNG: Bạn PHẢI trả lời HOÀN TOÀN bằng tiếng Việt. Không được sử dụng tiếng Anh hoặc ngôn ngữ khác.

Cuộc trò chuyện:
{conversation_str}

Hãy cung cấp một tóm tắt có cấu trúc tốt với:
1. Các chủ đề chính được thảo luận
2. Các điểm quan trọng hoặc quyết định
3. Thông tin quan trọng được chia sẻ
4. Bất kỳ hành động hoặc bước tiếp theo nào được đề cập

Giữ tóm tắt rõ ràng và đầy đủ thông tin.
"""
            
            # Generate summary
            summary = await self._generate_response(prompt, temperature=0.3)
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return "Xin lỗi, tôi không thể tóm tắt cuộc trò chuyện này. Vui lòng thử lại."
    
    async def _generate_response(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate response using Gemini AI."""
        try:
            # Log the request
            logger.info(f"🚀 GEMINI REQUEST:")
            logger.info(f"Temperature: {temperature}")
            logger.info(f"Prompt: {prompt}")
            logger.info("=" * 80)
            
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.8,
                top_k=40,
                max_output_tokens=2048,  # Increased from 1024 to allow longer responses
            )
            
            # Generate response
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=generation_config
            )
            
            # Log the raw response
            logger.info(f"📥 GEMINI RAW RESPONSE:")
            logger.info(f"Response object: {response}")
            if hasattr(response, 'candidates') and response.candidates:
                logger.info(f"Candidates count: {len(response.candidates)}")
                for i, candidate in enumerate(response.candidates):
                    logger.info(f"Candidate {i}: {candidate}")
                    if hasattr(candidate, 'finish_reason'):
                        logger.info(f"Finish reason: {candidate.finish_reason}")
            logger.info("=" * 80)
            
            # Check if response was blocked by safety filters
            if not response.candidates:
                error_msg = "Xin lỗi, tôi không thể trả lời câu hỏi này do chính sách an toàn."
                logger.warning("🚫 Response was blocked by safety filters")
                logger.info(f"❌ RETURNING ERROR: {error_msg}")
                return error_msg
            
            # Check for finish reason - handle both enum and integer values
            finish_reason = response.candidates[0].finish_reason
            reason_name = None
            reason_value = None
            
            if finish_reason:
                # Handle both enum (with .name) and integer values
                if hasattr(finish_reason, 'name'):
                    reason_name = finish_reason.name
                    reason_value = finish_reason.value if hasattr(finish_reason, 'value') else finish_reason
                else:
                    reason_value = finish_reason
                    # Map integer values to names (based on Gemini API documentation)
                    reason_names = {
                        0: "FINISH_REASON_UNSPECIFIED",
                        1: "STOP",
                        2: "MAX_TOKENS", 
                        3: "SAFETY",
                        4: "RECITATION",
                        5: "OTHER"
                    }
                    reason_name = reason_names.get(reason_value, "UNKNOWN")
                
                logger.warning(f"🚦 Response finished with reason: {reason_name} ({reason_value})")
                
                # Only return early for SAFETY blocks - for MAX_TOKENS, try to extract partial text
                if reason_name == "SAFETY":
                    error_msg = "Xin lỗi, tôi không thể trả lời câu hỏi này do chính sách an toàn."
                    logger.info(f"❌ SAFETY BLOCK: {error_msg}")
                    return error_msg
                elif reason_name == "MAX_TOKENS":
                    logger.info("⚠️ MAX_TOKENS reached, but will try to extract partial text")
                    # Continue to text extraction instead of returning error immediately
            
            # Handle both simple and complex responses
            try:
                # Try to get simple text response first
                text_response = response.text
                if text_response and text_response.strip():
                    final_response = text_response.strip()
                    logger.info(f"✅ GEMINI FINAL RESPONSE: {final_response}")
                    return final_response
                else:
                    logger.warning("Response text is empty, trying complex extraction")
                    raise ValueError("Empty response text")
            except ValueError as e:
                logger.debug(f"Simple text access failed: {e}")
                # If response is not simple text, use parts accessor
                try:
                    if response.candidates and len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        if candidate.content and candidate.content.parts and len(candidate.content.parts) > 0:
                            part = candidate.content.parts[0]
                            if hasattr(part, 'text') and part.text and part.text.strip():
                                final_response = part.text.strip()
                                logger.info(f"✅ GEMINI FINAL RESPONSE (from complex): {final_response}")
                                return final_response
                    
                    # If we get here, try to extract any text from the response
                    logger.warning(f"Complex response structure, trying to extract text...")
                    logger.debug(f"Response candidates: {len(response.candidates) if response.candidates else 0}")
                    
                    if response.candidates:
                        for i, candidate in enumerate(response.candidates):
                            logger.debug(f"Candidate {i}: {candidate}")
                            if candidate.content:
                                logger.debug(f"Content parts: {len(candidate.content.parts) if candidate.content.parts else 0}")
                                if candidate.content.parts:
                                    for j, part in enumerate(candidate.content.parts):
                                        logger.debug(f"Part {j}: {type(part)} - {part}")
                                        if hasattr(part, 'text') and part.text and part.text.strip():
                                            final_response = part.text.strip()
                                            logger.info(f"✅ GEMINI FINAL RESPONSE (from deep search): {final_response}")
                                            return final_response
                    
                    logger.warning("Could not extract text from Gemini response")
                    logger.debug(f"Full response object: {response}")
                    
                    # Check if this was a MAX_TOKENS issue and provide appropriate error
                    if reason_name == "MAX_TOKENS":
                        error_msg = "Xin lỗi, câu trả lời quá dài. Vui lòng hỏi câu hỏi ngắn gọn hơn."
                        logger.info(f"❌ MAX_TOKENS NO TEXT: {error_msg}")
                        return error_msg
                    else:
                        error_msg = "Xin lỗi, tôi không thể tạo ra câu trả lời lúc này. Vui lòng thử lại."
                        logger.info(f"❌ EXTRACTION FAILED: {error_msg}")
                        return error_msg
                
                except Exception as extract_error:
                    error_msg = "Xin lỗi, tôi gặp lỗi khi xử lý câu trả lời. Vui lòng thử lại."
                    logger.error(f"❌ EXTRACTION ERROR: {extract_error}")
                    logger.info(f"❌ RETURNING ERROR: {error_msg}")
                    return error_msg
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            raise
    
    def _build_context_string(self, context_messages: List[Dict]) -> str:
        """Build context string from recent messages."""
        if not context_messages:
            return "No recent context available."
        
        context_lines = []
        for msg in context_messages[-7:]:  # Last 7 messages for context
            timestamp = msg.get('timestamp', 'Unknown time')
            username = msg.get('username', 'Unknown user')
            text = msg.get('message_text', '')
            
            if text:
                context_lines.append(f"[{timestamp}] {username}: {text}")
        
        return "\n".join(context_lines) if context_lines else "No recent context available."
    
    def _build_conversation_string(self, messages: List[Dict]) -> str:
        """Build conversation string from message history."""
        if not messages:
            return "No messages to summarize."
        
        conversation_lines = []
        for msg in messages:
            timestamp = msg.get('timestamp', 'Unknown time')
            username = msg.get('username', 'Unknown user')
            text = msg.get('message_text', '')
            
            if text:
                conversation_lines.append(f"[{timestamp}] {username}: {text}")
        
        return "\n".join(conversation_lines) if conversation_lines else "No messages to summarize."
    
    def extract_username_from_mention(self, text: str) -> Optional[str]:
        """Extract username from @mention in text."""
        # Find @username pattern
        mentions = re.findall(r'@(\w+)', text)
        return mentions[0] if mentions else None
    
    def extract_key_value_from_text(self, text: str) -> Dict[str, str]:
        """Extract key-value pairs from natural language text."""
        # This is a simplified version - in production, you'd want more sophisticated parsing
        patterns = {
            'phone': r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})',
            'email': r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            'url': r'(https?://[^\s]+)',
            'bank_account': r'(\d{6,20})',
        }
        
        extracted = {}
        for key, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                extracted[key] = matches[0]
        
        return extracted 