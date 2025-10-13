"""
OpenAI API Integration Module

This module handles route generation for delivery trips using OpenAI API.
Generates turn-by-turn directions and calculates timestamps for delivery sequences.

Features:
- Simple route generation from address list
- Turn-by-turn direction generation
- Unix timestamp calculation with delivery buffers
- Error handling and retry logic
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from utils.timezone import get_est_now
import openai
from openai import OpenAIError, RateLimitError, APIError
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class OpenAIClient:
    """
    OpenAI API client for delivery route generation.
    
    Generates turn-by-turn directions for delivery routes with proper
    timing calculations including 15-minute delivery buffers.
    """
    
    def __init__(self):
        """Initialize OpenAI API client with configuration."""
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model = "gpt-3.5-turbo"
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        
        # Dynamic token limits based on route complexity
        self.max_tokens_short = 800   # 1-3 stops
        self.max_tokens_medium = 1200 # 4-6 stops  
        self.max_tokens_long = 1500   # 7+ stops
        
        # Route chunking thresholds
        self.max_stops_per_chunk = 5  # Maximum stops per chunk for long routes
        
        # Origin address (warehouse)
        self.origin_address = "47 Lower Main St, Portland, CT"
        
        logger.info("OpenAI API client initialized successfully")
    
    def generate_route_segments(self, addresses: List[str], delivery_date: str, approx_start_time: str) -> Optional[List[Dict[str, Any]]]:
        """
        Generate route segments with turn-by-turn directions and timestamps.
        
        Args:
            addresses: List of delivery addresses in order
            delivery_date: Delivery date (YYYY-MM-DD format)
            approx_start_time: Approximate start time (YYYY-MM-DD HH:MM AM/PM format)
            
        Returns:
            List of route segments with departure_time, arrival_time, and route directions
            Each segment includes Unix timestamps and 15-minute delivery buffers
            
        Example:
            addresses = ["100 Location 1, City 1, CT", "200 Location 2, City 2, CT"]
            delivery_date = "2025-08-05"
            approx_start_time = "2025-08-05 07:00 AM"
            
            Returns:
            [
                {
                    "departure_time": 1743897600,
                    "arrival_time": 1743898500,
                    "route": "Turn-by-turn directions from origin to location 1"
                },
                {
                    "departure_time": 1743899400,
                    "arrival_time": 1743900300,
                    "route": "Turn-by-turn directions from location 1 to location 2"
                }
            ]
        """
        logger.info(f"Generating route segments for {len(addresses)} addresses")
        
        if not addresses:
            logger.error("No addresses provided for route generation")
            return None
        
        try:
            # Check if route needs chunking (long routes)
            if len(addresses) > self.max_stops_per_chunk:
                logger.info(f"Route has {len(addresses)} stops, using chunking strategy")
                return self._generate_chunked_route(addresses, delivery_date, approx_start_time)
            
            # Generate route for shorter routes
            return self._generate_single_route(addresses, delivery_date, approx_start_time)
            
        except Exception as e:
            logger.error(f"Route generation failed: {str(e)}")
            return None
    
    def _generate_single_route(self, addresses: List[str], delivery_date: str, approx_start_time: str) -> Optional[List[Dict[str, Any]]]:
        """Generate route for a single chunk of addresses."""
        try:
            # Create enhanced prompt for route generation
            prompt = self._create_route_prompt(addresses, delivery_date, approx_start_time)
            
            # Calculate optimal token limit
            max_tokens = self._calculate_optimal_tokens(len(addresses))
            
            # Make API request with validation
            response = self._make_completion_request(prompt, max_tokens)
            if not response:
                return None
            
            # Validate response completeness
            if not self._validate_response_completeness(response):
                logger.warning("Response appears incomplete, attempting retry")
                response = self._make_completion_request(prompt, max_tokens)
                if not response or not self._validate_response_completeness(response):
                    logger.error("Failed to get complete response after retry")
                    return None
            
            # Parse response
            route_segments = self._parse_route_response(response)
            if not route_segments:
                return None
            
            # Post-process directions for quality improvement
            route_segments = self._post_process_directions(route_segments)
            
            # Calculate timestamps with delivery buffers
            route_segments = self._calculate_timestamps(route_segments, delivery_date, approx_start_time)
            
            logger.info(f"Generated {len(route_segments)} route segments successfully")
            return route_segments
            
        except Exception as e:
            logger.error(f"Single route generation failed: {str(e)}")
            return None
    
    def _generate_chunked_route(self, addresses: List[str], delivery_date: str, approx_start_time: str) -> Optional[List[Dict[str, Any]]]:
        """Generate route by splitting long routes into manageable chunks."""
        try:
            all_route_segments = []
            current_time = approx_start_time
            
            # Split addresses into chunks
            chunks = self._chunk_addresses(addresses)
            logger.info(f"Split {len(addresses)} addresses into {len(chunks)} chunks")
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)} with {len(chunk)} addresses")
                
                # Generate route for this chunk
                chunk_segments = self._generate_single_route(chunk, delivery_date, current_time)
                if not chunk_segments:
                    logger.error(f"Failed to generate route for chunk {i+1}")
                    return None
                
                # Adjust timestamps for continuity between chunks
                if i > 0 and all_route_segments:
                    last_arrival = all_route_segments[-1]['arrival_time']
                    time_adjustment = last_arrival - chunk_segments[0]['departure_time']
                    
                    for segment in chunk_segments:
                        segment['departure_time'] += time_adjustment
                        segment['arrival_time'] += time_adjustment
                
                all_route_segments.extend(chunk_segments)
                
                # Update current time for next chunk
                if chunk_segments:
                    current_time = datetime.fromtimestamp(chunk_segments[-1]['arrival_time']).strftime('%Y-%m-%d %I:%M %p')
            
            logger.info(f"Successfully generated chunked route with {len(all_route_segments)} total segments")
            return all_route_segments
            
        except Exception as e:
            logger.error(f"Chunked route generation failed: {str(e)}")
            return None
    
    def _chunk_addresses(self, addresses: List[str]) -> List[List[str]]:
        """Split addresses into manageable chunks."""
        chunks = []
        for i in range(0, len(addresses), self.max_stops_per_chunk):
            chunk = addresses[i:i + self.max_stops_per_chunk]
            chunks.append(chunk)
        return chunks
    
    def _calculate_optimal_tokens(self, num_stops: int) -> int:
        """Calculate optimal token limit based on number of stops."""
        if num_stops <= 3:
            return self.max_tokens_short
        elif num_stops <= 6:
            return self.max_tokens_medium
        else:
            return self.max_tokens_long
    
    def _validate_response_completeness(self, response: str) -> bool:
        """Validate that the response is complete and properly formatted."""
        try:
            # Check for basic JSON structure
            if not response.strip().startswith('[') or not response.strip().endswith(']'):
                return False
            
            # Check for balanced brackets
            open_brackets = response.count('[')
            close_brackets = response.count(']')
            if open_brackets != close_brackets:
                return False
            
            # Check for required fields in each segment
            if '"departure_time"' not in response or '"arrival_time"' not in response or '"route"' not in response:
                return False
            
            # Try to parse as JSON to validate structure
            json.loads(response)
            return True
            
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Response validation failed: {str(e)}")
            return False
    
    def _post_process_directions(self, route_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Post-process route directions to improve quality and reduce repetition."""
        for segment in route_segments:
            route_text = segment.get('route', '')
            if not route_text:
                continue
            
            # Reduce repetitive patterns
            route_text = self._reduce_repetitive_patterns(route_text)
            
            # Standardize street name formatting
            route_text = self._standardize_street_names(route_text)
            
            # Optimize length if too verbose
            if len(route_text) > 1500:
                route_text = self._truncate_route_description(route_text)
            
            segment['route'] = route_text
        
        return route_segments
    
    def _reduce_repetitive_patterns(self, route_text: str) -> str:
        """Reduce repetitive turn instructions in route text."""
        # Count repetitive patterns
        turn_left_count = route_text.lower().count('turn left')
        turn_right_count = route_text.lower().count('turn right')
        continue_straight_count = route_text.lower().count('continue straight')
        
        # If too many repetitive turns, simplify the description
        if turn_left_count > 6 or turn_right_count > 6 or continue_straight_count > 8:
            # Keep only the most important turns and simplify others
            lines = route_text.split('. ')
            important_lines = []
            turn_count = 0
            
            for line in lines:
                if 'turn left' in line.lower() or 'turn right' in line.lower():
                    turn_count += 1
                    if turn_count <= 4:  # Keep first 4 important turns
                        important_lines.append(line)
                elif 'continue straight' not in line.lower() or continue_straight_count <= 3:
                    important_lines.append(line)
                elif 'merge' in line.lower() or 'take exit' in line.lower() or 'follow' in line.lower():
                    important_lines.append(line)
            
            route_text = '. '.join(important_lines)
            if not route_text.endswith('.'):
                route_text += '.'
        
        return route_text
    
    def _standardize_street_names(self, route_text: str) -> str:
        """Standardize street name formatting."""
        # Common street name abbreviations
        replacements = {
            'street': 'St',
            'avenue': 'Ave', 
            'road': 'Rd',
            'drive': 'Dr',
            'lane': 'Ln',
            'boulevard': 'Blvd',
            'highway': 'Hwy',
            'route': 'Rt'
        }
        
        for full_name, abbrev in replacements.items():
            # Replace full names with abbreviations (case insensitive)
            route_text = route_text.replace(f' {full_name} ', f' {abbrev} ')
            route_text = route_text.replace(f' {full_name}.', f' {abbrev}.')
            route_text = route_text.replace(f' {full_name},', f' {abbrev},')
        
        return route_text
    
    def _truncate_route_description(self, route_text: str) -> str:
        """Truncate overly long route descriptions while preserving key information."""
        if len(route_text) <= 1500:
            return route_text
        
        # Split into sentences and keep the most important ones
        sentences = route_text.split('. ')
        important_sentences = []
        current_length = 0
        
        for sentence in sentences:
            if current_length + len(sentence) > 1400:  # Leave room for "..."
                break
            important_sentences.append(sentence)
            current_length += len(sentence) + 2  # +2 for ". "
        
        truncated_text = '. '.join(important_sentences)
        if truncated_text and not truncated_text.endswith('.'):
            truncated_text += '.'
        
        if len(truncated_text) < len(route_text):
            truncated_text += " [Route continues with similar directions]"
        
        return truncated_text
    
    def _create_route_prompt(self, addresses: List[str], delivery_date: str, approx_start_time: str) -> str:
        """Create enhanced prompt for route generation with quality improvements."""
        addresses_text = ""
        for i, address in enumerate(addresses, 1):
            addresses_text += f"{i}. {address}\n"
        
        return f"""
You are a professional delivery driver providing turn-by-turn directions. Generate high-quality, concise directions for a cannabis delivery route following the exact sequence provided.

ORIGIN LOCATION:
{self.origin_address}

DELIVERY SEQUENCE (follow this exact order):
{addresses_text}

DELIVERY DATE: {delivery_date}
APPROXIMATE START TIME: {approx_start_time}

QUALITY REQUIREMENTS:
1. Generate turn-by-turn directions from origin to each delivery location in the exact sequence provided
2. Do NOT reorder or optimize the route - follow the user's specified sequence
3. Provide clear, step-by-step driving directions between each point
4. Include specific street names and turns
5. Account for typical traffic conditions in Connecticut
6. Provide realistic travel time estimates (excluding 15-minute delivery buffers)
7. Format for easy reading by delivery drivers
8. Note: 15-minute delivery buffers will be automatically added between stops

DIRECTION QUALITY STANDARDS:
- Use major highways and roads when possible for efficiency
- Focus on major roads, highways, and significant turns only
- Do not include every minor street or intersection
- If the route involves long distances, use highway directions primarily
- Vary your language - avoid repetitive phrases like "Turn left" multiple times
- Use descriptive language: "Merge onto I-91 N", "Take exit 29A", "Continue on Main St"
- Keep each route segment under 400 words - be concise and practical
- Use proper street abbreviations: St, Ave, Rd, Dr, Blvd, Hwy, etc.

ANTI-REPETITION RULES:
- Do not repeat "Turn left" or "Turn right" more than 2 times in a single route segment
- Do not use "Continue straight" more than 1 time in a single route segment
- Vary your language: use "Merge onto", "Take exit", "Follow", "Continue on", "Head", "Proceed", etc.
- Use different sentence structures to avoid monotony
- Prioritize highway and major road directions over local street turns
- Use descriptive language: "Merge onto I-91 N", "Take exit 29A for Capitol Area", "Follow Main St"

OUTPUT FORMAT (JSON array):
[
    {{
        "departure_time": "YYYY-MM-DDTHH:MM:SS format for departure from previous location",
        "arrival_time": "YYYY-MM-DDTHH:MM:SS format for arrival at this location", 
        "route": "string of high-quality, varied turn-by-turn directions (max 400 words)"
    }}
]

CRITICAL: Provide only valid JSON response, no additional text or markdown formatting. Ensure response is complete and properly formatted.
"""
    
    def _make_completion_request(self, prompt: str, max_tokens: int = None) -> Optional[str]:
        """Make completion request to OpenAI API with error handling."""
        if max_tokens is None:
            max_tokens = self.max_tokens_medium  # Default to medium token limit
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Making OpenAI API request (attempt {attempt + 1}) with {max_tokens} tokens")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a professional delivery route expert specializing in cannabis delivery logistics. Generate practical, efficient routes with realistic travel times and clear directions. Focus on major roads and highways when possible. Vary your language to avoid repetitive patterns and provide high-quality, professional directions."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                    timeout=30
                )
                
                if response.choices and response.choices[0].message.content:
                    content = response.choices[0].message.content.strip()
                    logger.debug(f"OpenAI API request successful. Response: {content[:200]}...")
                    return content
                else:
                    logger.error("OpenAI API returned empty response")
                    return None
                    
            except RateLimitError as e:
                logger.warning(f"Rate limit exceeded (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                else:
                    logger.error("Max retries exceeded for rate limit")
                    return None
                    
            except APIError as e:
                logger.error(f"OpenAI API error (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    return None
                    
            except Exception as e:
                logger.error(f"Unexpected error in OpenAI request: {str(e)}")
                return None
        
        return None
    
    def _parse_route_response(self, response: str) -> Optional[List[Dict[str, Any]]]:
        """Parse route response from OpenAI with improved validation."""
        try:
            # Debug: Log the actual response for troubleshooting
            logger.debug(f"Raw OpenAI response length: {len(response)} characters")
            logger.debug(f"Raw OpenAI response start: {response[:200]}...")
            logger.debug(f"Raw OpenAI response end: {response[-200:]}...")
            
            # Clean the response - remove markdown code blocks if present
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
                logger.debug("Removed ```json prefix")
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
                logger.debug("Removed ``` prefix")
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
                logger.debug("Removed ``` suffix")
            
            cleaned_response = cleaned_response.strip()
            logger.debug(f"Cleaned response length: {len(cleaned_response)} characters")
            logger.debug(f"Cleaned response start: {cleaned_response[:200]}...")
            
            # Extract JSON from response
            json_start = cleaned_response.find('[')
            json_end = cleaned_response.rfind(']') + 1
            
            logger.debug(f"JSON start position: {json_start}")
            logger.debug(f"JSON end position: {json_end}")
            
            if json_start == -1:
                logger.error("No opening bracket '[' found in route response")
                logger.error(f"Full response: {response}")
                return None
            
            if json_end == 0:
                logger.error("No closing bracket ']' found in route response")
                logger.error(f"Full response: {response}")
                return None
            
            json_str = cleaned_response[json_start:json_end]
            logger.debug(f"Extracted JSON length: {len(json_str)} characters")
            logger.debug(f"Extracted JSON start: {json_str[:200]}...")
            
            # Enhanced validation - check for incomplete JSON
            if not self._validate_json_completeness(json_str):
                logger.error("JSON appears incomplete or malformed")
                return None
            
            # Try to parse the JSON
            try:
                route_segments = json.loads(json_str)
                logger.debug(f"Successfully parsed JSON into {len(route_segments)} segments")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {str(e)}")
                logger.error(f"Attempted to parse: {json_str[:500]}...")
                return None
            
            # Validate structure
            if not isinstance(route_segments, list):
                logger.error("Route response is not a list")
                return None
            
            # Validate each segment
            for i, segment in enumerate(route_segments):
                if not isinstance(segment, dict):
                    logger.error(f"Route segment {i} is not a dictionary")
                    return None
                if 'departure_time' not in segment or 'arrival_time' not in segment or 'route' not in segment:
                    logger.error(f"Route segment {i} missing required fields")
                    return None
                
                # Validate route content quality
                route_text = segment.get('route', '')
                if len(route_text) > 1500:  # Route too long
                    logger.warning(f"Route segment {i} is very long ({len(route_text)} chars)")
                if route_text.count('Turn left') > 10 or route_text.count('Turn right') > 10:
                    logger.warning(f"Route segment {i} has too many repetitive turns")
            
            logger.info(f"Successfully parsed {len(route_segments)} route segments")
            return route_segments
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse route JSON: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error parsing route response: {str(e)}")
            return None
    
    def _validate_json_completeness(self, json_str: str) -> bool:
        """Validate that JSON string is complete and properly formatted."""
        try:
            # Check for balanced brackets
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')
            if open_brackets != close_brackets:
                logger.debug(f"Unbalanced brackets: {open_brackets} open, {close_brackets} close")
                return False
            
            # Check for balanced braces
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            if open_braces != close_braces:
                logger.debug(f"Unbalanced braces: {open_braces} open, {close_braces} close")
                return False
            
            # Check for required fields
            if '"departure_time"' not in json_str or '"arrival_time"' not in json_str or '"route"' not in json_str:
                logger.debug("Missing required fields in JSON")
                return False
            
            # Check for proper array structure
            if not json_str.strip().startswith('[') or not json_str.strip().endswith(']'):
                logger.debug("JSON is not a proper array")
                return False
            
            # Try to parse as JSON to validate structure
            json.loads(json_str)
            return True
            
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"JSON completeness validation failed: {str(e)}")
            return False
    
    def _calculate_timestamps(self, route_segments: List[Dict[str, Any]], delivery_date: str, approx_start_time: str) -> List[Dict[str, Any]]:
        """
        Calculate Unix timestamps for departure and arrival times with 15-minute buffers.
        
        Args:
            route_segments: Route segments from OpenAI response
            delivery_date: Delivery date (YYYY-MM-DD)
            approx_start_time: Approximate start time (YYYY-MM-DD HH:MM AM/PM)
            
        Returns:
            Route segments with calculated Unix timestamps
        """
        try:
            # Parse delivery date and start time
            try:
                # Parse the approximate start time
                start_datetime = datetime.strptime(approx_start_time, '%Y-%m-%d %I:%M %p')
            except ValueError:
                # Fallback to delivery date with 8 AM start
                start_datetime = datetime.strptime(delivery_date, '%Y-%m-%d')
                start_datetime = start_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
                logger.warning("Invalid start time format, using 8 AM as default")
            
            # Convert to EST timezone
            from utils.timezone import US_EASTERN
            if start_datetime.tzinfo is None:
                start_datetime = start_datetime.replace(tzinfo=US_EASTERN)
            
            current_time = start_datetime
            
            for i, segment in enumerate(route_segments):
                # Convert ISO format timestamps to Unix timestamps
                try:
                    # Parse the departure time from ISO format
                    departure_iso = segment.get('departure_time', '')
                    if departure_iso:
                        departure_dt = datetime.fromisoformat(departure_iso.replace('Z', '+00:00'))
                        departure_timestamp = int(departure_dt.timestamp())
                    else:
                        departure_timestamp = int(current_time.timestamp())
                    
                    # Parse the arrival time from ISO format
                    arrival_iso = segment.get('arrival_time', '')
                    if arrival_iso:
                        arrival_dt = datetime.fromisoformat(arrival_iso.replace('Z', '+00:00'))
                        arrival_timestamp = int(arrival_dt.timestamp())
                    else:
                        # Calculate based on departure + travel time
                        arrival_timestamp = departure_timestamp + (15 * 60)  # 15 minutes default
                    
                    # Update the segment with Unix timestamps
                    segment['departure_time'] = departure_timestamp
                    segment['arrival_time'] = arrival_timestamp
                    
                    # Update current time for next segment
                    current_time = datetime.fromtimestamp(arrival_timestamp)
                    
                    # Add 15-minute buffer for delivery processing (except for last stop)
                    if i < len(route_segments) - 1:
                        current_time += timedelta(minutes=15)
                    
                    logger.debug(f"Segment {i+1}: Departure at {datetime.fromtimestamp(departure_timestamp).strftime('%H:%M')}, "
                               f"Arrival at {datetime.fromtimestamp(arrival_timestamp).strftime('%H:%M')}")
                    
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing timestamps for segment {i+1}: {str(e)}")
                    # Fallback to calculated timestamps
                    departure_timestamp = int(current_time.timestamp())
                    current_time += timedelta(minutes=15)  # Default travel time
                    arrival_timestamp = int(current_time.timestamp())
                    
                    segment['departure_time'] = departure_timestamp
                    segment['arrival_time'] = arrival_timestamp
                    
                    # Add 15-minute buffer for delivery processing (except for last stop)
                    if i < len(route_segments) - 1:
                        current_time += timedelta(minutes=15)
            
            logger.info(f"Calculated timestamps for {len(route_segments)} route segments")
            return route_segments
            
        except Exception as e:
            logger.error(f"Error calculating timestamps: {str(e)}")
            return route_segments 