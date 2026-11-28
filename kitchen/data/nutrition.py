"""Approximate nutrition for every built-in ingredient, and how much common kitchen measures weigh.

Values are per 100 g of the ingredient as it goes into the pot (dals, rice and flours are dry/raw;
"Chickpeas (boiled)", "Leftover rice" and the other leftovers are cooked). They are rounded averages
from standard food tables (Indian Food Composition Tables and USDA FoodData Central). Real food varies
with variety, brand and cooking, so the app always shows calories as estimates ("about 230 kcal").

Each row: id: (kcal, protein g, carbs g, fat g, fibre g, grams in 1 cup, grams in 1 piece, other measures)
- "1 cup" means a 240 ml kitchen cup, filled the way people usually fill it (chopped, grated, loose).
- "1 piece" is one medium item (1 onion, 1 egg, 1 slice of bread...). None if it isn't counted in pieces.
- Other measures: tsp / tbsp when they are not simply 1/48 and 1/16 of a cup, and bunch, handful, clove, inch...
"""

NUTRITION = {
    # ---- Vegetables
    'onion': (40, 1.1, 9.3, 0.1, 1.7, 160, 110),
    'tomato': (18, 0.9, 3.9, 0.2, 1.2, 180, 100),
    'potato': (77, 2.0, 17.0, 0.1, 2.2, 150, 150),
    'garlic': (149, 6.4, 33.0, 0.5, 2.1, 136, 4, {'clove': 4}),
    'ginger': (80, 1.8, 18.0, 0.8, 2.0, 96, 6, {'inch': 6}),
    'green_chilli': (40, 2.0, 9.5, 0.2, 1.5, 100, 4),
    'coriander': (23, 2.1, 3.7, 0.5, 2.8, 16, 1, {'handful': 10, 'bunch': 100}),
    'curry_leaves': (108, 6.1, 18.7, 1.0, 6.4, 10, 0.1, {'handful': 3}),
    'spinach': (23, 2.9, 3.6, 0.4, 2.2, 30, 30, {'bunch': 250, 'handful': 30}),
    'methi': (49, 4.4, 6.0, 0.9, 1.1, 20, 20, {'bunch': 100, 'handful': 20}),
    'cauliflower': (25, 1.9, 5.0, 0.3, 2.0, 107, 500),
    'cabbage': (25, 1.3, 5.8, 0.1, 2.5, 70, 700),
    'carrot': (41, 0.9, 9.6, 0.2, 2.8, 128, 70),
    'peas': (81, 5.4, 14.5, 0.4, 5.1, 145, 1),
    'capsicum': (20, 0.9, 4.6, 0.2, 1.7, 92, 120),
    'brinjal': (25, 1.0, 5.9, 0.2, 3.0, 82, 150),
    'okra': (33, 1.9, 7.5, 0.2, 3.2, 100, 12),
    'beans': (31, 1.8, 7.0, 0.2, 2.7, 110, 6),
    'cucumber': (15, 0.7, 3.6, 0.1, 0.5, 120, 200),
    'lemon': (22, 0.4, 6.9, 0.2, 0.3, 240, 30),  # the juice: half a lemon gives about 15 g
    'mushroom': (22, 3.1, 3.3, 0.3, 1.0, 70, 15),
    'spring_onion': (32, 1.8, 7.3, 0.2, 2.6, 100, 15),
    'drumstick': (37, 2.1, 8.5, 0.2, 3.2, 100, 60),
    'bottle_gourd': (15, 0.6, 3.4, 0.0, 0.5, 116, 700),
    'sweet_corn': (86, 3.3, 19.0, 1.4, 2.0, 145, 100),
    'beetroot': (43, 1.6, 9.6, 0.2, 2.8, 136, 130),
    'sweet_potato': (86, 1.6, 20.0, 0.1, 3.0, 133, 130),
    'pumpkin': (26, 1.0, 6.5, 0.1, 0.5, 116, 1000),
    'ridge_gourd': (20, 1.2, 4.4, 0.2, 1.1, 100, 200),
    'bitter_gourd': (17, 1.0, 3.7, 0.2, 2.8, 94, 100),
    'radish': (16, 0.7, 3.4, 0.1, 1.6, 116, 120),
    'raw_banana': (122, 1.3, 31.9, 0.4, 2.3, 148, 150),
    'mint': (44, 3.8, 8.4, 0.7, 6.8, 20, 0.2, {'handful': 10, 'bunch': 50}),
    # ---- Fruits
    'banana': (89, 1.1, 23.0, 0.3, 2.6, 150, 100),
    'apple': (52, 0.3, 14.0, 0.2, 2.4, 125, 180),
    'mango': (60, 0.8, 15.0, 0.4, 1.6, 165, 200),
    'papaya': (43, 0.5, 11.0, 0.3, 1.7, 145, 500),
    # ---- Dairy & eggs
    'milk': (62, 3.2, 4.8, 3.3, 0, 245, 245),
    'curd': (61, 3.5, 4.7, 3.3, 0, 245, 245),
    'paneer': (265, 18.3, 1.2, 20.8, 0, 150, 25),
    'butter': (717, 0.9, 0.1, 81.0, 0, 227, 10, {'tsp': 5, 'tbsp': 14}),
    'ghee': (900, 0, 0, 99.8, 0, 205, 5, {'tsp': 4.5, 'tbsp': 13}),
    'cream': (250, 2.0, 3.0, 25.0, 0, 240, 15),
    'cheese': (330, 20.0, 4.0, 26.0, 0, 100, 20, {'slice': 20}),
    'egg': (143, 12.6, 0.7, 9.5, 0, 243, 50),
    # ---- Meat & fish (raw, the part you eat)
    'chicken': (140, 20.0, 0, 6.5, 0, 140, 100),
    'mutton': (180, 18.5, 0, 12.0, 0, 140, 100),
    'fish': (110, 19.0, 0, 3.5, 0, 140, 80, {'slice': 80}),
    'prawns': (85, 20.0, 0.9, 0.5, 0, 145, 12),
    # ---- Grains & flours (dry)
    'rice': (356, 7.1, 78.0, 0.5, 1.3, 185, None),
    'atta': (341, 12.1, 69.4, 1.7, 11.2, 120, None),
    'maida': (351, 10.3, 74.0, 1.0, 2.7, 125, None),
    'besan': (387, 22.0, 58.0, 6.7, 10.8, 92, None),
    'sooji': (360, 12.7, 73.0, 1.0, 3.9, 167, None),
    'poha': (346, 6.6, 77.0, 1.2, 2.8, 65, None),
    'bread': (265, 9.0, 49.0, 3.2, 2.7, 30, 25, {'slice': 25}),
    'noodles': (400, 9.0, 65.0, 12.0, 2.5, 70, 70, {'packet': 70}),
    'pasta': (371, 13.0, 75.0, 1.5, 3.2, 100, None),
    'oats': (389, 16.9, 66.0, 6.9, 10.6, 80, None),
    'sabudana': (351, 0.2, 87.0, 0.1, 0.9, 152, None),
    'dosa_batter': (150, 4.5, 29.0, 0.6, 1.5, 240, None),
    'vermicelli': (352, 11.0, 75.0, 1.0, 2.7, 75, None),
    'ragi': (328, 7.3, 72.0, 1.3, 11.5, 120, None),
    'jowar': (349, 10.4, 72.6, 1.9, 9.7, 120, None),
    'bajra': (361, 11.6, 67.5, 5.0, 11.5, 120, None),
    'kuttu': (343, 13.0, 71.5, 3.4, 10.0, 120, None),
    'samak': (307, 6.2, 65.5, 2.2, 9.8, 170, None),
    'rajgira': (371, 13.6, 65.0, 7.0, 6.7, 120, None),
    'singhara': (330, 3.4, 78.0, 0.5, 2.0, 120, None),
    'makhana': (347, 9.7, 76.9, 0.1, 14.5, 28, 0.6),
    # ---- Dals & beans (dry, unless the name says boiled)
    'toor_dal': (343, 22.0, 57.0, 1.5, 9.0, 200, None),
    'moong_dal': (347, 24.0, 59.0, 1.2, 8.0, 200, None),
    'masoor_dal': (352, 24.6, 59.0, 1.1, 10.8, 192, None),
    'chana_dal': (360, 20.8, 59.8, 5.6, 12.0, 200, None),
    'urad_dal': (341, 25.0, 59.0, 1.6, 12.0, 200, None),
    'chickpeas': (164, 8.9, 27.4, 2.6, 7.6, 164, None),
    'sprouts': (70, 7.0, 12.0, 0.4, 3.0, 100, None),
    'peanuts': (567, 25.8, 16.0, 49.0, 8.5, 146, 1, {'tbsp': 9}),
    'cashew': (553, 18.0, 30.0, 44.0, 3.3, 130, 1.5, {'tbsp': 9}),
    'rajma': (333, 23.6, 60.0, 0.8, 15.0, 184, None),
    'kala_chana': (360, 20.0, 61.0, 5.0, 17.0, 200, None),
    'lobia': (336, 23.5, 60.0, 1.3, 10.6, 170, None),
    'soya_chunks': (345, 52.0, 33.0, 0.5, 13.0, 50, None),
    # ---- Spices (a teaspoon of powder weighs 2-3 g)
    'turmeric': (312, 9.7, 67.0, 3.3, 22.7, None, None, {'tsp': 3}),
    'red_chilli_powder': (282, 13.5, 50.0, 14.0, 35.0, None, None, {'tsp': 2.7}),
    'coriander_powder': (298, 12.4, 55.0, 17.8, 41.9, None, None, {'tsp': 2}),
    'cumin': (375, 17.8, 44.0, 22.0, 10.5, None, None, {'tsp': 2.1}),
    'mustard_seeds': (508, 26.0, 28.0, 36.0, 12.0, None, None, {'tsp': 3.3}),
    'garam_masala': (379, 13.0, 50.0, 15.0, 25.0, None, None, {'tsp': 2}),
    'hing': (297, 4.0, 68.0, 1.0, 4.0, None, None, {'tsp': 2}),
    'kasuri_methi': (300, 23.0, 50.0, 6.4, 24.0, None, None, {'tsp': 0.6}),
    'chaat_masala': (250, 10.0, 45.0, 5.0, 15.0, None, None, {'tsp': 3}),
    'sambar_powder': (330, 13.0, 50.0, 10.0, 20.0, None, None, {'tsp': 2.3}),
    'rasam_powder': (330, 13.0, 50.0, 10.0, 20.0, None, None, {'tsp': 2.3}),
    'black_pepper': (251, 10.4, 64.0, 3.3, 25.0, None, None, {'tsp': 2.3}),
    'whole_spices': (300, 6.0, 70.0, 10.0, 30.0, None, 0.3, {'tsp': 2, 'clove': 0.1}),
    'cardamom': (311, 11.0, 68.0, 6.7, 28.0, None, 0.2, {'tsp': 2}),
    'dry_red_chilli': (318, 12.0, 57.0, 17.0, 27.0, None, 0.7, {'tsp': 1}),
    'tamarind': (239, 2.8, 62.5, 0.6, 5.1, None, 10, {'tsp': 6, 'lemon-sized': 15}),
    'sesame': (573, 17.7, 23.0, 49.7, 11.8, None, None, {'tsp': 3}),
    # ---- Basics & sauces
    'salt': (0, 0, 0, 0, 0, None, None, {'tsp': 6}),
    'oil': (884, 0, 0, 100.0, 0, 218, None, {'tsp': 4.5, 'tbsp': 13.6}),
    'water': (0, 0, 0, 0, 0, 240, None),
    'sugar': (387, 0, 100.0, 0, 0, 200, None, {'tsp': 4.2, 'tbsp': 12.5}),
    'jaggery': (383, 0.4, 98.0, 0.1, 0, 200, None, {'tsp': 4.5, 'tbsp': 14}),
    'soy_sauce': (53, 8.1, 4.9, 0.6, 0.8, 255, None, {'tsp': 5.3, 'tbsp': 16}),
    'tomato_ketchup': (112, 1.3, 26.0, 0.1, 0.3, 270, None, {'tsp': 5.7, 'tbsp': 17}),
    'vinegar': (18, 0, 0, 0, 0, 240, None, {'tsp': 5}),
    'coconut': (354, 3.3, 15.0, 33.5, 9.0, 80, None, {'tbsp': 5}),
    'coconut_milk': (200, 2.0, 3.0, 21.0, 0, 240, None),
    # ---- Leftovers (cooked)
    'leftover_rice': (130, 2.7, 28.0, 0.3, 0.4, 160, None),
    'leftover_roti': (290, 9.0, 55.0, 4.0, 8.0, None, 40),
    'leftover_dal': (110, 6.0, 15.0, 3.0, 3.0, 240, None),
    'leftover_sabzi': (90, 2.5, 10.0, 4.5, 3.0, 180, None),
}

FIELDS = ('kcal', 'protein', 'carbs', 'fat', 'fibre')


def split(row):
    """A row -> ({'kcal': .., 'protein': .., ...} per 100 g, {'cup': .., 'piece': .., 'tsp': ..} in grams)"""
    per100 = dict(zip(FIELDS, row[:5]))
    cup, piece = row[5], row[6]
    measures = {k: v for k, v in {'cup': cup, 'piece': piece}.items() if v is not None}
    if len(row) > 7:
        measures.update(row[7])
    return per100, measures
