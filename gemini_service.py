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
            
            # Create conversation prompt
            prompt = f"""
You are a helpful AI assistant in a Telegram group chat. Your personality should be {tone}.

Context from recent messages:
{context_str}

Current message: "{message}"

Please respond naturally and helpfully. Keep responses concise but informative.
Maintain a {tone} tone throughout your response.
"""
            
            # Generate response
            response = await self._generate_response(prompt, temperature)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Sorry, I'm having trouble processing your message right now. Please try again."
    
    async def summarize_conversation(self, messages: List[Dict]) -> str:
        """Summarize a conversation from message history."""
        try:
            # Build conversation string
            conversation_str = self._build_conversation_string(messages)
            
            # Create summarization prompt
            prompt = f"""
Please provide a concise summary of this conversation. Focus on the main topics discussed, key decisions made, and important information shared.

Conversation:
{conversation_str}

Please provide a well-structured summary with:
1. Main topics discussed
2. Key points or decisions
3. Important information shared
4. Any action items or next steps mentioned

Keep the summary clear and informative.
"""
            
            # Generate summary
            summary = await self._generate_response(prompt, temperature=0.3)
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return "Sorry, I couldn't summarize the conversation. Please try again."
    
    async def _generate_response(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate response using Gemini AI."""
        try:
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.8,
                top_k=40,
                max_output_tokens=1024,
            )
            
            # Generate response
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=generation_config
            )
            
            return response.text
            
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