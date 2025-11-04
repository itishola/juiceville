import os
from PIL import Image, ImageDraw, ImageFont

def create_icon(size, color, filename):
    """Create a simple icon with the given size and color"""
    try:
        # Create a new image with transparent background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Calculate safe margins (at least 20% of size)
        margin = max(4, int(size * 0.2))
        
        # Draw a filled circle/rectangle as the main icon
        if size >= 32:
            # For larger icons, draw a circle
            draw.ellipse([margin, margin, size-margin, size-margin], fill=color)
            
            # Add a simple "J" letter for Juiceville (only on larger icons)
            if size >= 72:
                try:
                    # Calculate font size based on icon size
                    font_size = max(12, int(size * 0.4))
                    font = ImageFont.truetype("arial.ttf", font_size)
                    
                    # Calculate text position
                    bbox = draw.textbbox((0, 0), "J", font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (size - text_width) // 2
                    y = (size - text_height) // 2
                    
                    # Draw the text in white
                    draw.text((x, y), "J", fill="white", font=font)
                except:
                    # If font loading fails, draw a simple white rectangle
                    rect_margin = margin + int(size * 0.3)
                    rect_size = size - 2 * rect_margin
                    if rect_size > 0:
                        draw.rectangle([rect_margin, rect_margin, 
                                      size-rect_margin, size-rect_margin], 
                                     fill="white")
        else:
            # For very small icons, just draw a filled square
            draw.rectangle([0, 0, size, size], fill=color)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Save the icon
        img.save(filename)
        print(f"Created: {filename}")
        
    except Exception as e:
        print(f"Error creating {filename}: {e}")

def main():
    # Define the output directory
    icons_dir = "orders/static/orders/img/icons"
    
    # Brand color (orange for juice)
    brand_color = (255, 165, 0, 255)  # Orange with alpha
    
    # Create PWA icons in various sizes
    sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    
    for size in sizes:
        create_icon(size, brand_color, f'{icons_dir}/icon-{size}x{size}.png')
    
    # Create favicon sizes
    create_icon(32, brand_color, f'{icons_dir}/favicon-32x32.png')
    create_icon(16, brand_color, f'{icons_dir}/favicon-16x16.png')
    
    # Create Apple touch icon (180x180 is recommended)
    create_icon(180, brand_color, f'{icons_dir}/apple-touch-icon.png')
    
    print("All icons generated successfully!")

if __name__ == "__main__":
    main()