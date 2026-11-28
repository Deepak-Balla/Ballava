"""Ballava ingredient catalog.

Each row: (id, display name, category, days it usually lasts once bought or None if it keeps
for months, other names people type (Hindi / Telugu / Tamil / English, comma separated),
optional extras such as allergens or diet).
"""

CATEGORIES = ['Vegetables', 'Fruits', 'Dairy & Eggs', 'Meat & Fish', 'Grains & Flours', 'Dals & Beans', 'Spices', 'Basics & Sauces', 'Leftovers']

# Always assumed to be in every kitchen, never counted as "missing".
ASSUMED = ['salt', 'oil', 'water']

RAW = [
    # Vegetables
    ('onion', 'Onion', 'Vegetables', 30, 'pyaz, pyaaz, kanda, ullipaya, ullipayalu, vengayam, onions'),
    ('tomato', 'Tomato', 'Vegetables', 5, 'tamatar, tamater, takkali, tamata, tomatoes'),
    ('potato', 'Potato', 'Vegetables', 30, 'aloo, alu, batata, bangaladumpa, urulaikizhangu, potatoes'),
    ('garlic', 'Garlic', 'Vegetables', 30, 'lehsun, lahsun, lasun, vellulli, poondu, garlic cloves'),
    ('ginger', 'Ginger', 'Vegetables', 14, 'adrak, adrakh, allam, inji'),
    ('green_chilli', 'Green chilli', 'Vegetables', 7, 'hari mirch, harimirch, mirchi, pachimirchi, pachi mirapakaya, green chili, green chillies, green chilies, chilli, chillies, chili, chilies'),
    ('coriander', 'Coriander leaves', 'Vegetables', 4, 'dhaniya, dhania, cilantro, kothimeera, kothamalli, coriander leaves, hara dhaniya, coriander'),
    ('curry_leaves', 'Curry leaves', 'Vegetables', 7, 'kadi patta, kadipatta, karivepaku, kariveppilai, curry leaf, curry leaves'),
    ('spinach', 'Spinach', 'Vegetables', 3, 'palak, palakura, keerai, paalak'),
    ('methi', 'Fenugreek leaves', 'Vegetables', 3, 'methi leaves, methi, menthi kura, fenugreek, fenugreek leaves'),
    ('cauliflower', 'Cauliflower', 'Vegetables', 5, 'gobi, gobhi, phool gobi, phoolgobi'),
    ('cabbage', 'Cabbage', 'Vegetables', 10, 'patta gobi, band gobhi, bandh gobi, muttakose'),
    ('carrot', 'Carrot', 'Vegetables', 14, 'gajar, carrots'),
    ('peas', 'Green peas', 'Vegetables', 5, 'matar, mutter, green peas, batani, pachi batani, peas'),
    ('capsicum', 'Capsicum', 'Vegetables', 6, 'shimla mirch, bell pepper, bell peppers, capsicums'),
    ('brinjal', 'Brinjal', 'Vegetables', 5, 'baingan, baigan, eggplant, aubergine, vankaya, kathirikai, brinjals'),
    ('okra', 'Okra', 'Vegetables', 3, 'bhindi, bhendi, lady finger, ladies finger, ladyfinger, bendakaya, vendakkai'),
    ('beans', 'French beans', 'Vegetables', 5, 'green beans, french beans, phali, beans'),
    ('cucumber', 'Cucumber', 'Vegetables', 6, 'kheera, khira, kakdi, dosakaya, vellarikka, cucumbers'),
    ('lemon', 'Lemon', 'Vegetables', 14, 'nimbu, limbu, nimmakaya, elumichai, lime, lemons, limes'),
    ('mushroom', 'Mushroom', 'Vegetables', 3, 'mushrooms, khumb'),
    ('spring_onion', 'Spring onion', 'Vegetables', 4, 'hara pyaz, scallion, scallions, green onion, spring onions'),
    ('drumstick', 'Drumstick', 'Vegetables', 5, 'moringa, munagakaya, murungakkai, sahjan, drumsticks'),
    ('bottle_gourd', 'Bottle gourd', 'Vegetables', 7, 'lauki, dudhi, ghiya, sorakaya, suraikkai'),
    ('sweet_corn', 'Sweet corn', 'Vegetables', 5, 'corn, bhutta, makka, sweetcorn'),
    ('beetroot', 'Beetroot', 'Vegetables', 14, 'chukandar, beet, beets'),
    ('sweet_potato', 'Sweet potato', 'Vegetables', 14, 'shakarkandi, shakarkand, chilagada dumpa, sweet potatoes'),
    ('pumpkin', 'Pumpkin', 'Vegetables', 14, 'kaddu, sitaphal, gummadikaya, parangikai'),
    ('ridge_gourd', 'Ridge gourd', 'Vegetables', 5, 'turai, tori, beerakaya, peerkangai'),
    ('bitter_gourd', 'Bitter gourd', 'Vegetables', 5, 'karela, kakarakaya, pavakkai'),
    ('radish', 'Radish', 'Vegetables', 7, 'mooli, mullangi, radishes'),
    ('raw_banana', 'Raw banana', 'Vegetables', 6, 'kaccha kela, kachcha kela, aratikaya, vazhakkai, plantain, raw plantain, raw bananas'),
    ('mint', 'Mint leaves', 'Vegetables', 4, 'pudina, pudeena, mint'),
    # Fruits
    ('banana', 'Banana', 'Fruits', 4, 'kela, kele, arati pandu, vazhaipazham, bananas'),
    ('apple', 'Apple', 'Fruits', 14, 'seb, apples'),
    ('mango', 'Mango', 'Fruits', 5, 'aam, mamidi, maanga, mangoes'),
    ('papaya', 'Papaya', 'Fruits', 4, 'papita, boppayi'),
    # Dairy & Eggs
    ('milk', 'Milk', 'Dairy & Eggs', 3, 'doodh, dudh, paalu, paal', {'allergens': ['dairy']}),
    ('curd', 'Curd', 'Dairy & Eggs', 5, 'dahi, yogurt, yoghurt, perugu, thayir, mosaru', {'allergens': ['dairy']}),
    ('paneer', 'Paneer', 'Dairy & Eggs', 4, 'cottage cheese', {'allergens': ['dairy']}),
    ('butter', 'Butter', 'Dairy & Eggs', 30, 'makhan, makkhan, venna', {'allergens': ['dairy']}),
    ('ghee', 'Ghee', 'Dairy & Eggs', None, 'neyyi, nei, clarified butter', {'allergens': ['dairy']}),
    ('cream', 'Fresh cream', 'Dairy & Eggs', 5, 'malai, fresh cream, cream', {'allergens': ['dairy']}),
    ('cheese', 'Cheese', 'Dairy & Eggs', 20, 'cheese slices, cheese cubes', {'allergens': ['dairy']}),
    ('egg', 'Eggs', 'Dairy & Eggs', 14, 'anda, ande, guddu, gudlu, muttai, eggs', {'allergens': ['egg'], 'diet': 'egg'}),
    # Meat & Fish
    ('chicken', 'Chicken', 'Meat & Fish', 2, 'murgh, murg, kodi, koli, kozhi', {'diet': 'nonveg'}),
    ('mutton', 'Mutton', 'Meat & Fish', 2, 'gosht, lamb, goat meat, mamsam', {'diet': 'nonveg'}),
    ('fish', 'Fish', 'Meat & Fish', 1, 'machli, machhi, chepa, meen', {'allergens': ['seafood'], 'diet': 'nonveg'}),
    ('prawns', 'Prawns', 'Meat & Fish', 1, 'jhinga, shrimp, shrimps, royyalu, eral, prawn', {'allergens': ['seafood'], 'diet': 'nonveg'}),
    # Grains & Flours
    ('rice', 'Rice (raw)', 'Grains & Flours', None, 'chawal, chaval, biyyam, arisi, basmati, sona masoori, raw rice'),
    ('atta', 'Wheat flour (atta)', 'Grains & Flours', None, 'wheat flour, gehun ka atta, chapati flour, godhuma pindi', {'allergens': ['gluten']}),
    ('maida', 'Maida', 'Grains & Flours', None, 'all purpose flour, plain flour, refined flour', {'allergens': ['gluten']}),
    ('besan', 'Besan', 'Grains & Flours', None, 'gram flour, chickpea flour, senaga pindi, kadalai maavu'),
    ('sooji', 'Sooji (rava)', 'Grains & Flours', None, 'suji, rava, rawa, semolina, upma rava, bombay rava', {'allergens': ['gluten']}),
    ('poha', 'Poha', 'Grains & Flours', None, 'flattened rice, beaten rice, aval, atukulu, avalakki'),
    ('bread', 'Bread', 'Grains & Flours', 4, 'pav, bread slices, loaf', {'allergens': ['gluten']}),
    ('noodles', 'Noodles', 'Grains & Flours', None, 'maggi, instant noodles, hakka noodles, chowmein', {'allergens': ['gluten']}),
    ('pasta', 'Pasta', 'Grains & Flours', None, 'penne, macaroni, spaghetti, fusilli', {'allergens': ['gluten']}),
    ('oats', 'Oats', 'Grains & Flours', None, 'rolled oats, oatmeal'),
    ('sabudana', 'Sabudana', 'Grains & Flours', None, 'tapioca pearls, sago, saggubiyyam, javvarisi'),
    ('dosa_batter', 'Idli/dosa batter', 'Grains & Flours', 4, 'dosa batter, idli batter, idli dosa batter, dosa pindi, idli pindi, dosa maavu'),
    ('vermicelli', 'Vermicelli', 'Grains & Flours', None, 'semiya, seviyan, sevai', {'allergens': ['gluten']}),
    ('ragi', 'Ragi flour', 'Grains & Flours', None, 'nachni, finger millet, ragi flour, ragi pindi, kezhvaragu'),
    ('jowar', 'Jowar flour', 'Grains & Flours', None, 'sorghum, jonna pindi, cholam, jowar flour'),
    ('bajra', 'Bajra flour', 'Grains & Flours', None, 'pearl millet, sajja pindi, kambu, bajra flour'),
    ('kuttu', 'Kuttu flour', 'Grains & Flours', None, 'buckwheat flour, kuttu ka atta'),
    ('samak', 'Samak rice', 'Grains & Flours', None, 'vrat ke chawal, barnyard millet, sama rice, bhagar'),
    ('rajgira', 'Rajgira flour', 'Grains & Flours', None, 'amaranth flour, rajgira atta, ramdana, rajgira'),
    ('singhara', 'Singhara flour', 'Grains & Flours', None, 'water chestnut flour, singhara atta, singhade ka atta, singhara'),
    ('makhana', 'Makhana', 'Grains & Flours', None, 'fox nuts, foxnuts, lotus seeds, phool makhana, phul makhana'),
    # Dals & Beans
    ('toor_dal', 'Toor dal', 'Dals & Beans', None, 'arhar dal, arhar, tuvar dal, toor, tur dal, pigeon pea, kandi pappu, thuvaram paruppu, dal'),
    ('moong_dal', 'Moong dal', 'Dals & Beans', None, 'yellow moong, split moong, pesara pappu, pesarapappu, pasi paruppu, mung dal, moong'),
    ('masoor_dal', 'Masoor dal', 'Dals & Beans', None, 'red lentils, masoor, lentils'),
    ('chana_dal', 'Chana dal', 'Dals & Beans', None, 'senaga pappu, kadalai paruppu, bengal gram'),
    ('urad_dal', 'Urad dal', 'Dals & Beans', None, 'minapappu, minappappu, ulundu, ulutham paruppu, urad'),
    ('chickpeas', 'Chickpeas (boiled/canned)', 'Dals & Beans', 3, 'chana, chole, kabuli chana, boiled chana, chickpea, garbanzo'),
    ('sprouts', 'Moong sprouts', 'Dals & Beans', 3, 'sprouted moong, moong sprouts, mulake, sprout'),
    ('peanuts', 'Peanuts', 'Dals & Beans', None, 'moongphali, mungfali, groundnut, groundnuts, palli, pallilu, verkadalai, shengdana, peanut', {'allergens': ['nuts']}),
    ('cashew', 'Cashews', 'Dals & Beans', None, 'kaju, jeedipappu, mundiri, cashew nuts, cashew', {'allergens': ['nuts']}),
    ('rajma', 'Rajma', 'Dals & Beans', None, 'kidney beans, red beans, rajmah'),
    ('kala_chana', 'Kala chana', 'Dals & Beans', None, 'black chana, black chickpeas, nalla senagalu, kondakadalai'),
    ('lobia', 'Lobia', 'Dals & Beans', None, 'black eyed peas, chawli, alasandalu, karamani'),
    ('soya_chunks', 'Soya chunks', 'Dals & Beans', None, 'soya, soyabean chunks, nutrela, meal maker'),
    # Spices
    ('turmeric', 'Turmeric', 'Spices', None, 'haldi, pasupu, manjal'),
    ('red_chilli_powder', 'Red chilli powder', 'Spices', None, 'lal mirch, chilli powder, chili powder, karam, mirchi powder, kashmiri chilli, red chilli'),
    ('coriander_powder', 'Coriander powder', 'Spices', None, 'dhaniya powder, dhania powder, dhaniyalu podi'),
    ('cumin', 'Cumin seeds', 'Spices', None, 'jeera, zeera, jeelakarra, jeerakam, cumin seeds'),
    ('mustard_seeds', 'Mustard seeds', 'Spices', None, 'rai, sarson, avalu, kadugu, mustard'),
    ('garam_masala', 'Garam masala', 'Spices', None, 'garam masala powder'),
    ('hing', 'Hing', 'Spices', None, 'asafoetida, inguva, perungayam'),
    ('kasuri_methi', 'Kasuri methi', 'Spices', None, 'dried fenugreek leaves, dried methi'),
    ('chaat_masala', 'Chaat masala', 'Spices', None, 'chat masala'),
    ('sambar_powder', 'Sambar powder', 'Spices', None, 'sambar masala, sambhar powder, sambar podi'),
    ('rasam_powder', 'Rasam powder', 'Spices', None, 'rasam masala, charu podi, rasam podi'),
    ('black_pepper', 'Black pepper', 'Spices', None, 'kali mirch, miriyalu, milagu, pepper, pepper powder'),
    ('whole_spices', 'Whole spices', 'Spices', None, 'khada masala, bay leaf, tej patta, cloves, laung, cinnamon, dalchini'),
    ('cardamom', 'Cardamom', 'Spices', None, 'elaichi, elachi, yelakulu, elakkai'),
    ('dry_red_chilli', 'Dry red chilli', 'Spices', None, 'sukhi lal mirch, sabut lal mirch, endu mirapakaya, vara milagai, dried red chilli, red chillies'),
    ('tamarind', 'Tamarind', 'Spices', None, 'imli, chintapandu, puli'),
    ('sesame', 'Sesame seeds', 'Spices', None, 'til, nuvvulu, ellu'),
    # Basics & Sauces
    ('salt', 'Salt', 'Basics & Sauces', None, 'namak, uppu'),
    ('oil', 'Cooking oil', 'Basics & Sauces', None, 'tel, nune, enna, sunflower oil, mustard oil, groundnut oil, cooking oil'),
    ('water', 'Water', 'Basics & Sauces', None, 'pani, paani, neellu'),
    ('sugar', 'Sugar', 'Basics & Sauces', None, 'cheeni, chini, shakkar, panchadara'),
    ('jaggery', 'Jaggery', 'Basics & Sauces', None, 'gud, gur, bellam, vellam'),
    ('soy_sauce', 'Soy sauce', 'Basics & Sauces', None, 'soya sauce, soy'),
    ('tomato_ketchup', 'Tomato ketchup', 'Basics & Sauces', None, 'ketchup, tomato sauce'),
    ('vinegar', 'Vinegar', 'Basics & Sauces', None, 'sirka'),
    ('coconut', 'Coconut (grated)', 'Basics & Sauces', 4, 'nariyal, kobbari, thengai, grated coconut, fresh coconut'),
    ('coconut_milk', 'Coconut milk', 'Basics & Sauces', 3, 'nariyal doodh'),
    # Leftovers
    ('leftover_rice', 'Leftover rice', 'Leftovers', 1, 'cooked rice, leftover chawal, left over chawal, leftover annam, bacha hua chawal, baasi chawal, basi chawal, annam, left over rice, yesterday rice, yesterdays rice'),
    ('leftover_roti', 'Leftover roti', 'Leftovers', 1, 'leftover rotis, chapati, chapatis, chapathi, roti, rotis, phulka, leftover chapati', {'allergens': ['gluten']}),
    ('leftover_dal', 'Leftover dal', 'Leftovers', 2, 'cooked dal, leftover pappu, left over dal'),
    ('leftover_sabzi', 'Leftover sabzi', 'Leftovers', 1, 'cooked sabzi, leftover curry, leftover vegetables, leftover sabji, left over sabzi'),
]

INGREDIENTS = [
    {
        'id': id_, 'name': name, 'category': category, 'shelfDays': shelf,
        'aliases': [a.strip() for a in aliases.split(',') if a.strip()],
        'allergens': (extra[0] if extra else {}).get('allergens', []),
        'diet': (extra[0] if extra else {}).get('diet', 'veg'),
    }
    for id_, name, category, shelf, aliases, *extra in RAW
]

BY_ID = {i['id']: i for i in INGREDIENTS}

# Calories, protein, carbs, fat and fibre per 100 g, and what a cup / piece weighs (see nutrition.py).
from .nutrition import NUTRITION, split  # noqa: E402

for _ing in INGREDIENTS:
    _ing['nutrition'], _ing['measures'] = split(NUTRITION[_ing['id']])

# Jain cooking avoids onion, garlic and root vegetables.
JAIN_BLOCKED = ['onion', 'garlic', 'potato', 'carrot', 'beetroot', 'sweet_potato', 'ginger', 'mushroom', 'spring_onion']
ONION_GARLIC = ['onion', 'garlic', 'spring_onion']

# One-tap "kits" so a new user can fill the kitchen in seconds.
KITS = [{'id': 'masala',
  'name': 'Masala box',
  'items': ['turmeric', 'red_chilli_powder', 'coriander_powder', 'cumin', 'mustard_seeds', 'garam_masala', 'hing', 'sugar']},
 {'id': 'basics',
  'name': 'Everyday basics',
  'items': ['rice', 'atta', 'toor_dal', 'onion', 'tomato', 'potato', 'ginger', 'garlic', 'green_chilli']},
 {'id': 'south',
  'name': 'South Indian tadka',
  'items': ['mustard_seeds', 'urad_dal', 'chana_dal', 'dry_red_chilli', 'hing', 'curry_leaves', 'tamarind', 'sambar_powder']}]
