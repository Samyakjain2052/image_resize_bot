import telebot
from PIL import Image, ImageOps
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

class ImageSizeManager:
    @staticmethod
    def increase_image_size(img, target_size_bytes, format_name):
        """Increase image size using multiple techniques"""
        techniques = [
            ('metadata', ImageSizeManager._add_metadata),
            ('scaling', ImageSizeManager._increase_by_scaling),
            ('padding', ImageSizeManager._increase_by_padding),
            ('quality', ImageSizeManager._increase_by_quality),
            ('duplicate', ImageSizeManager._increase_by_duplicate)
        ]
        
        for technique_name, technique in techniques:
            logger.info(f"Trying to increase size using {technique_name}")
            result = technique(img, target_size_bytes, format_name)
            if result and ImageSizeManager._verify_size(result, target_size_bytes, format_name):
                return result
        return None

    @staticmethod
    def _verify_size(img, target_size_bytes, format_name):
        """Verify if the processed image meets the size requirement"""
        img_io = io.BytesIO()
        img.save(img_io, format=format_name, quality=100)
        return len(img_io.getvalue()) >= target_size_bytes

    @staticmethod
    def _add_metadata(img, target_size_bytes, format_name):
        """Add metadata to increase file size"""
        metadata = {"Comment": "x" * 1024}  # Start with 1KB of metadata
        max_iterations = 10
        
        for _ in range(max_iterations):
            img_io = io.BytesIO()
            img.save(img_io, format=format_name, quality=100, **metadata)
            if len(img_io.getvalue()) >= target_size_bytes:
                return img
            metadata["Comment"] = metadata["Comment"] * 2
        return None

    @staticmethod
    def _increase_by_scaling(img, target_size_bytes, format_name):
        """Increase size by scaling up the image"""
        width, height = img.size
        max_scale = 4.0
        scale_factor = 1.2
        
        while scale_factor <= max_scale:
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            enlarged = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            for quality in range(95, 101):
                img_io = io.BytesIO()
                enlarged.save(img_io, format=format_name, quality=quality)
                if len(img_io.getvalue()) >= target_size_bytes:
                    return enlarged
            
            scale_factor *= 1.2
        return None

    @staticmethod
    def _increase_by_padding(img, target_size_bytes, format_name):
        """Increase size by adding padding"""
        padding = 100
        max_padding = 1000
        
        while padding <= max_padding:
            padded = ImageOps.expand(img, border=padding, fill=(255, 255, 255))
            img_io = io.BytesIO()
            padded.save(img_io, format=format_name, quality=100)
            if len(img_io.getvalue()) >= target_size_bytes:
                return padded
            padding *= 2
        return None

    @staticmethod
    def _increase_by_quality(img, target_size_bytes, format_name):
        """Increase size by adjusting quality settings"""
        for quality in range(95, 101):
            img_io = io.BytesIO()
            img.save(img_io, format=format_name, quality=quality, optimize=False)
            if len(img_io.getvalue()) >= target_size_bytes:
                return img
        return None

    @staticmethod
    def _increase_by_duplicate(img, target_size_bytes, format_name):
        """Increase size by duplicating the image"""
        width, height = img.size
        multiplier = 2
        max_multiplier = 4
        
        while multiplier <= max_multiplier:
            new_height = height * multiplier
            new_img = Image.new('RGB', (width, new_height))
            
            for i in range(multiplier):
                new_img.paste(img, (0, i * height))
            
            img_io = io.BytesIO()
            new_img.save(img_io, format=format_name, quality=100)
            if len(img_io.getvalue()) >= target_size_bytes:
                return new_img
            multiplier += 1
        return None

# ... Rest of your existing code remains the same ...

class ImageProcessor:
    SUPPORTED_FORMATS = {'JPG': 'JPEG', 'JPEG': 'JPEG', 'PNG': 'PNG', 'WEBP': 'WEBP'}
    
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
    def process_image(image_data, target_size, output_format):
        """Process image with size control"""
        try:
            if output_format not in ImageProcessor.SUPPORTED_FORMATS:
                raise ValueError(f"Unsupported format: {output_format}")
            
            pil_format = ImageProcessor.SUPPORTED_FORMATS[output_format]
            min_size_bytes, max_size_bytes = target_size
            
            # Open and convert image
            img = Image.open(io.BytesIO(image_data))
            if pil_format == 'JPEG':
                img = img.convert("RGB")
            
            current_size = len(image_data)
            logger.info(f"Original size: {ImageProcessor.get_size_in_appropriate_unit(current_size)}")
            
            # If current size is too small, try increasing
            if current_size < min_size_bytes:
                logger.info("Attempting to increase image size")
                enlarged_img = ImageSizeManager.increase_image_size(img, min_size_bytes, pil_format)
                
                if enlarged_img:
                    # Verify the size is within bounds
                    img_io = io.BytesIO()
                    enlarged_img.save(img_io, format=pil_format, quality=95)
                    new_size = len(img_io.getvalue())
                    
                    if min_size_bytes <= new_size <= max_size_bytes:
                        logger.info(f"Successfully increased size to {ImageProcessor.get_size_in_appropriate_unit(new_size)}")
                        return img_io.getvalue()
            
            # If current size is too large or increasing didn't work, try reducing
            if current_size > max_size_bytes or current_size < min_size_bytes:
                width, height = img.size
                scale_factor = 0.9
                
                while width > 100 and height > 100:
                    new_width = int(width * scale_factor)
                    new_height = int(height * scale_factor)
                    resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Try different quality settings
                    for quality in range(95, 4, -5):
                        img_io = io.BytesIO()
                        resized.save(img_io, format=pil_format, quality=quality)
                        new_size = len(img_io.getvalue())
                        
                        if min_size_bytes <= new_size <= max_size_bytes:
                            logger.info(f"Successfully resized to {ImageProcessor.get_size_in_appropriate_unit(new_size)}")
                            return img_io.getvalue()
                    
                    width, height = new_width, new_height
            
            logger.info("Failed to meet size constraints")
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
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"converted_{timestamp}.{output_format.lower()}"
                
                final_size = ImageProcessor.get_size_in_appropriate_unit(len(processed_image))
                original_size = ImageProcessor.get_size_in_appropriate_unit(len(downloaded_file))
                
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