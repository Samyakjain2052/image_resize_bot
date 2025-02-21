import telebot
from PIL import Image
import io
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_API_KEY")

if not TOKEN:
    raise ValueError("❌ TELEGRAM API Key not found! Check .env file.")

bot = telebot.TeleBot(TOKEN)
user_states = {}

class ImageProcessor:
    SUPPORTED_FORMATS = {'JPG': 'JPEG', 'JPEG': 'JPEG', 'PNG': 'PNG', 'WEBP': 'WEBP'}
    MAX_SCALING_FACTOR = 2.0  # Maximum scaling factor for enlarging images
    
    @staticmethod
    def convert_to_bytes(size_str):
        """Convert KB/MB size to bytes"""
        size = float(size_str.replace('MB', '').replace('KB', ''))
        if 'MB' in size_str.upper():
            return size * 1024 * 1024
        elif 'KB' in size_str.upper():
            return size * 1024
        return size
    
    @staticmethod
    def get_size_in_appropriate_unit(bytes_size):
        """Convert bytes to KB or MB as appropriate"""
        kb_size = bytes_size / 1024
        if kb_size >= 1024:
            return f"{kb_size/1024:.2f}MB"
        return f"{kb_size:.2f}KB"

    @staticmethod
    def try_save_image(img, format_name, target_size, width, height):
        """Try different quality settings to achieve target size"""
        for quality in range(95, 4, -5):
            img_resized = img.resize((width, height), Image.Resampling.LANCZOS)
            img_io = io.BytesIO()
            img_resized.save(img_io, format=format_name, quality=quality)
            current_size = len(img_io.getvalue())
            logger.info(f"Tried size {width}x{height} quality {quality}: {ImageProcessor.get_size_in_appropriate_unit(current_size)}")
            if current_size <= target_size:
                return img_io.getvalue(), current_size
        return None, None

    @staticmethod
    def process_image(image_data, target_size, output_format):
        """Process image with enhanced size control"""
        try:
            if output_format not in ImageProcessor.SUPPORTED_FORMATS:
                raise ValueError(f"Unsupported format: {output_format}")
            
            pil_format = ImageProcessor.SUPPORTED_FORMATS[output_format]
            min_size_bytes, max_size_bytes = target_size
            
            # Open and convert image
            img = Image.open(io.BytesIO(image_data))
            if pil_format == 'JPEG':
                img = img.convert("RGB")
            
            original_width, original_height = img.size
            current_size = len(image_data)
            
            logger.info(f"Processing image: Original size: {ImageProcessor.get_size_in_appropriate_unit(current_size)}")
            logger.info(f"Target size range: {ImageProcessor.get_size_in_appropriate_unit(min_size_bytes)} - {ImageProcessor.get_size_in_appropriate_unit(max_size_bytes)}")
            
            # If current size is too small, try enlarging
            if current_size < min_size_bytes:
                scale_factor = 1.1
                while scale_factor <= ImageProcessor.MAX_SCALING_FACTOR:
                    new_width = int(original_width * scale_factor)
                    new_height = int(original_height * scale_factor)
                    
                    img_io = io.BytesIO()
                    enlarged_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    enlarged_img.save(img_io, format=pil_format, quality=95)
                    new_size = len(img_io.getvalue())
                    
                    logger.info(f"Enlarged to {new_width}x{new_height}: {ImageProcessor.get_size_in_appropriate_unit(new_size)}")
                    
                    if min_size_bytes <= new_size <= max_size_bytes:
                        return img_io.getvalue()
                    elif new_size > max_size_bytes:
                        break
                    
                    scale_factor *= 1.1
            
            # If current size is too large or enlarging didn't work, try reducing
            if current_size > max_size_bytes or current_size < min_size_bytes:
                width = original_width
                height = original_height
                
                while width > 100 and height > 100:
                    result, size = ImageProcessor.try_save_image(img, pil_format, max_size_bytes, width, height)
                    if result and min_size_bytes <= size <= max_size_bytes:
                        return result
                    
                    # Reduce dimensions by 10%
                    width = int(width * 0.9)
                    height = int(height * 0.9)
            
            # If original size is within range, try different quality settings
            if min_size_bytes <= current_size <= max_size_bytes:
                img_io = io.BytesIO()
                img.save(img_io, format=pil_format, quality=95)
                return img_io.getvalue()
            
            logger.info("Failed to meet size constraints after all attempts")
            return None
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 Welcome to the Image Converter Bot!\n\n"
        "I can help you convert and resize images to specific formats and sizes.\n\n"
        "📝 Instructions:\n"
        "1. Send me an image\n"
        "2. Specify the desired size range (e.g., '2MB-3MB' or '500KB-1MB')\n"
        "3. Choose the output format (JPG, PNG, WEBP)\n\n"
        "Supported formats: JPG, PNG, WEBP\n"
        "Supported size units: KB, MB"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        user_id = message.from_user.id
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_size = file_info.file_size / 1024  # Convert to KB
        
        user_states[user_id] = {
            'file_id': file_id,
            'waiting_for': 'size_format',
            'original_size': file_size
        }
        
        bot.reply_to(
            message,
            f"📏 Current image size: {file_size:.2f}KB\n"
            "Please specify the target size range and format\n"
            "Format: <size_range> <format>\n"
            "Examples:\n"
            "2MB-3MB JPG\n"
            "500KB-1MB PNG"
        )
        
    except Exception as e:
        logger.error(f"Error handling photo: {str(e)}")
        bot.reply_to(message, "❌ Error processing your photo. Please try again.")

@bot.message_handler(func=lambda msg: (
    msg.from_user.id in user_states and
    user_states[msg.from_user.id].get('waiting_for') == 'size_format'
))
def handle_conversion_request(message):
    user_id = message.from_user.id
    
    try:
        # Parse input
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError("Invalid format. Please use: <size_range> <format>")
        
        size_range, output_format = parts
        output_format = output_format.upper()
        
        # Validate format
        if output_format not in ImageProcessor.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format. Please use: {', '.join(ImageProcessor.SUPPORTED_FORMATS.keys())}")
        
        # Parse size range with KB/MB support
        size_pattern = r'(\d+(?:\.\d+)?(?:MB|KB))-(\d+(?:\.\d+)?(?:MB|KB))'
        match = re.match(size_pattern, size_range, re.IGNORECASE)
        
        if not match:
            raise ValueError("Invalid size range format. Examples: 2MB-3MB, 500KB-1MB")
        
        min_size_str, max_size_str = match.groups()
        min_size_bytes = ImageProcessor.convert_to_bytes(min_size_str)
        max_size_bytes = ImageProcessor.convert_to_bytes(max_size_str)
        
        if min_size_bytes >= max_size_bytes:
            raise ValueError("Minimum size must be less than maximum size.")
        
        # Download and process image
        status_message = bot.reply_to(message, "⚙️ Processing your image...")
        
        file_id = user_states[user_id]['file_id']
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Process image
        try:
            processed_image = ImageProcessor.process_image(
                downloaded_file,
                (min_size_bytes, max_size_bytes),
                output_format
            )
            
            if processed_image:
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"converted_{timestamp}.{output_format.lower()}"
                
                final_size = ImageProcessor.get_size_in_appropriate_unit(len(processed_image))
                original_size = ImageProcessor.get_size_in_appropriate_unit(len(downloaded_file))
                
                # Send converted image
                bot.delete_message(message.chat.id, status_message.message_id)
                bot.send_document(
                    message.chat.id,
                    io.BytesIO(processed_image),
                    visible_file_name=filename,
                    caption=(
                        f"✅ Conversion successful!\n"
                        f"📊 Original size: {original_size}\n"
                        f"📊 Final size: {final_size}\n"
                        f"📎 Format: {output_format}"
                    )
                )
            else:
                bot.edit_message_text(
                    "❌ Could not process the image within the given constraints.\n"
                    "Try a different size range or format.",
                    message.chat.id,
                    status_message.message_id
                )
                
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            bot.edit_message_text(
                f"❌ Error processing image: {str(e)}",
                message.chat.id,
                status_message.message_id
            )
            
    except ValueError as ve:
        bot.reply_to(message, f"❌ {str(ve)}")
    except Exception as e:
        logger.error(f"Error in conversion request: {str(e)}")
        bot.reply_to(message, "❌ An error occurred. Please try again.")
    finally:
        if user_id in user_states:
            del user_states[user_id]

@bot.message_handler(func=lambda message: True)
def handle_invalid(message):
    bot.reply_to(
        message,
        "❌ Invalid input. Please send an image or use /help for instructions."
    )

if __name__ == "__main__":
    logger.info("Bot started")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")