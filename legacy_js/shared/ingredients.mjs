// Ballava ingredient catalog.
// Each ingredient: id, display name, category, other names people actually type
// (Hindi / Telugu / Tamil / English variants, comma separated), how many days it usually lasts
// once bought (null = keeps for months), and allergy / diet facts.

export const CATEGORIES = [
  'Vegetables', 'Fruits', 'Dairy & Eggs', 'Meat & Fish', 'Grains & Flours',
  'Dals & Beans', 'Spices', 'Basics & Sauces', 'Leftovers',
];

// Always assumed to be in every kitchen, never counted as "missing".
export const ASSUMED = ['salt', 'oil', 'water'];

// [id, name, category, shelfDays|null, aliases, extra]
const RAW = [
  // Vegetables
  ['onion', 'Onion', 'Vegetables', 30, 'pyaz, pyaaz, kanda, ullipaya, ullipayalu, vengayam, onions'],
  ['tomato', 'Tomato', 'Vegetables', 5, 'tamatar, tamater, takkali, tamata, tomatoes'],
  ['potato', 'Potato', 'Vegetables', 30, 'aloo, alu, batata, bangaladumpa, urulaikizhangu, potatoes'],
  ['garlic', 'Garlic', 'Vegetables', 30, 'lehsun, lahsun, lasun, vellulli, poondu, garlic cloves'],
  ['ginger', 'Ginger', 'Vegetables', 14, 'adrak, adrakh, allam, inji'],
  ['green_chilli', 'Green chilli', 'Vegetables', 7, 'hari mirch, harimirch, mirchi, pachimirchi, pachi mirapakaya, green chili, green chillies, green chilies, chilli, chillies, chili, chilies'],
  ['coriander', 'Coriander leaves', 'Vegetables', 4, 'dhaniya, dhania, cilantro, kothimeera, kothamalli, coriander leaves, hara dhaniya, coriander'],
  ['curry_leaves', 'Curry leaves', 'Vegetables', 7, 'kadi patta, kadipatta, karivepaku, kariveppilai, curry leaf, curry leaves'],
  ['spinach', 'Spinach', 'Vegetables', 3, 'palak, palakura, keerai, paalak'],
  ['methi', 'Fenugreek leaves', 'Vegetables', 3, 'methi leaves, methi, menthi kura, fenugreek, fenugreek leaves'],
  ['cauliflower', 'Cauliflower', 'Vegetables', 5, 'gobi, gobhi, phool gobi, phoolgobi'],
  ['cabbage', 'Cabbage', 'Vegetables', 10, 'patta gobi, band gobhi, bandh gobi, muttakose'],
  ['carrot', 'Carrot', 'Vegetables', 14, 'gajar, carrots'],
  ['peas', 'Green peas', 'Vegetables', 5, 'matar, mutter, green peas, batani, pachi batani, peas'],
  ['capsicum', 'Capsicum', 'Vegetables', 6, 'shimla mirch, bell pepper, bell peppers, capsicums'],
  ['brinjal', 'Brinjal', 'Vegetables', 5, 'baingan, baigan, eggplant, aubergine, vankaya, kathirikai, brinjals'],
  ['okra', 'Okra', 'Vegetables', 3, 'bhindi, bhendi, lady finger, ladies finger, ladyfinger, bendakaya, vendakkai'],
  ['beans', 'French beans', 'Vegetables', 5, 'green beans, french beans, phali, beans'],
  ['cucumber', 'Cucumber', 'Vegetables', 6, 'kheera, khira, kakdi, dosakaya, vellarikka, cucumbers'],
  ['lemon', 'Lemon', 'Vegetables', 14, 'nimbu, limbu, nimmakaya, elumichai, lime, lemons, limes'],
  ['mushroom', 'Mushroom', 'Vegetables', 3, 'mushrooms, khumb'],
  ['spring_onion', 'Spring onion', 'Vegetables', 4, 'hara pyaz, scallion, scallions, green onion, spring onions'],
  ['drumstick', 'Drumstick', 'Vegetables', 5, 'moringa, munagakaya, murungakkai, sahjan, drumsticks'],
  ['bottle_gourd', 'Bottle gourd', 'Vegetables', 7, 'lauki, dudhi, ghiya, sorakaya, suraikkai'],
  ['sweet_corn', 'Sweet corn', 'Vegetables', 5, 'corn, bhutta, makka, sweetcorn'],
  ['beetroot', 'Beetroot', 'Vegetables', 14, 'chukandar, beet, beets'],
  ['sweet_potato', 'Sweet potato', 'Vegetables', 14, 'shakarkandi, shakarkand, chilagada dumpa, sweet potatoes'],
  ['pumpkin', 'Pumpkin', 'Vegetables', 14, 'kaddu, sitaphal, gummadikaya, parangikai'],
  ['ridge_gourd', 'Ridge gourd', 'Vegetables', 5, 'turai, tori, beerakaya, peerkangai'],
  ['bitter_gourd', 'Bitter gourd', 'Vegetables', 5, 'karela, kakarakaya, pavakkai'],
  ['radish', 'Radish', 'Vegetables', 7, 'mooli, mullangi, radishes'],
  ['mint', 'Mint leaves', 'Vegetables', 4, 'pudina, pudeena, mint'],
  // Fruits
  ['banana', 'Banana', 'Fruits', 4, 'kela, kele, arati pandu, vazhaipazham, bananas'],
  ['apple', 'Apple', 'Fruits', 14, 'seb, apples'],
  ['mango', 'Mango', 'Fruits', 5, 'aam, mamidi, maanga, mangoes'],
  ['papaya', 'Papaya', 'Fruits', 4, 'papita, boppayi'],
  // Dairy & eggs
  ['milk', 'Milk', 'Dairy & Eggs', 3, 'doodh, dudh, paalu, paal', { allergens: ['dairy'] }],
  ['curd', 'Curd', 'Dairy & Eggs', 5, 'dahi, yogurt, yoghurt, perugu, thayir, mosaru', { allergens: ['dairy'] }],
  ['paneer', 'Paneer', 'Dairy & Eggs', 4, 'cottage cheese', { allergens: ['dairy'] }],
  ['butter', 'Butter', 'Dairy & Eggs', 30, 'makhan, makkhan, venna', { allergens: ['dairy'] }],
  ['ghee', 'Ghee', 'Dairy & Eggs', null, 'neyyi, nei, clarified butter', { allergens: ['dairy'] }],
  ['cream', 'Fresh cream', 'Dairy & Eggs', 5, 'malai, fresh cream, cream', { allergens: ['dairy'] }],
  ['cheese', 'Cheese', 'Dairy & Eggs', 20, 'cheese slices, cheese cubes', { allergens: ['dairy'] }],
  ['egg', 'Eggs', 'Dairy & Eggs', 14, 'anda, ande, guddu, gudlu, muttai, eggs', { allergens: ['egg'], diet: 'egg' }],
  // Meat & fish
  ['chicken', 'Chicken', 'Meat & Fish', 2, 'murgh, murg, kodi, koli, kozhi', { diet: 'nonveg' }],
  ['mutton', 'Mutton', 'Meat & Fish', 2, 'gosht, lamb, goat meat, mamsam', { diet: 'nonveg' }],
  ['fish', 'Fish', 'Meat & Fish', 1, 'machli, machhi, chepa, meen', { diet: 'nonveg', allergens: ['seafood'] }],
  ['prawns', 'Prawns', 'Meat & Fish', 1, 'jhinga, shrimp, shrimps, royyalu, eral, prawn', { diet: 'nonveg', allergens: ['seafood'] }],
  // Grains & flours
  ['rice', 'Rice (raw)', 'Grains & Flours', null, 'chawal, chaval, biyyam, arisi, basmati, sona masoori, raw rice'],
  ['atta', 'Wheat flour (atta)', 'Grains & Flours', null, 'wheat flour, gehun ka atta, chapati flour, godhuma pindi', { allergens: ['gluten'] }],
  ['maida', 'Maida', 'Grains & Flours', null, 'all purpose flour, plain flour, refined flour', { allergens: ['gluten'] }],
  ['besan', 'Besan', 'Grains & Flours', null, 'gram flour, chickpea flour, senaga pindi, kadalai maavu'],
  ['sooji', 'Sooji (rava)', 'Grains & Flours', null, 'suji, rava, rawa, semolina, upma rava, bombay rava', { allergens: ['gluten'] }],
  ['poha', 'Poha', 'Grains & Flours', null, 'flattened rice, beaten rice, aval, atukulu, avalakki'],
  ['bread', 'Bread', 'Grains & Flours', 4, 'pav, bread slices, loaf', { allergens: ['gluten'] }],
  ['noodles', 'Noodles', 'Grains & Flours', null, 'maggi, instant noodles, hakka noodles, chowmein', { allergens: ['gluten'] }],
  ['pasta', 'Pasta', 'Grains & Flours', null, 'penne, macaroni, spaghetti, fusilli', { allergens: ['gluten'] }],
  ['oats', 'Oats', 'Grains & Flours', null, 'rolled oats, oatmeal'],
  ['sabudana', 'Sabudana', 'Grains & Flours', null, 'tapioca pearls, sago, saggubiyyam, javvarisi'],
  ['dosa_batter', 'Idli/dosa batter', 'Grains & Flours', 4, 'dosa batter, idli batter, idli dosa batter, dosa pindi, idli pindi, dosa maavu'],
  ['vermicelli', 'Vermicelli', 'Grains & Flours', null, 'semiya, seviyan, sevai', { allergens: ['gluten'] }],
  ['ragi', 'Ragi flour', 'Grains & Flours', null, 'nachni, finger millet, ragi flour, ragi pindi, kezhvaragu'],
  ['jowar', 'Jowar flour', 'Grains & Flours', null, 'sorghum, jonna pindi, cholam, jowar flour'],
  ['bajra', 'Bajra flour', 'Grains & Flours', null, 'pearl millet, sajja pindi, kambu, bajra flour'],
  ['kuttu', 'Kuttu flour', 'Grains & Flours', null, 'buckwheat flour, kuttu ka atta'],
  ['samak', 'Samak rice', 'Grains & Flours', null, 'vrat ke chawal, barnyard millet, sama rice, bhagar'],
  // Dals & beans
  ['toor_dal', 'Toor dal', 'Dals & Beans', null, 'arhar dal, arhar, tuvar dal, toor, tur dal, pigeon pea, kandi pappu, thuvaram paruppu, dal'],
  ['moong_dal', 'Moong dal', 'Dals & Beans', null, 'yellow moong, split moong, pesara pappu, pesarapappu, pasi paruppu, mung dal, moong'],
  ['masoor_dal', 'Masoor dal', 'Dals & Beans', null, 'red lentils, masoor, lentils'],
  ['chana_dal', 'Chana dal', 'Dals & Beans', null, 'senaga pappu, kadalai paruppu, bengal gram'],
  ['urad_dal', 'Urad dal', 'Dals & Beans', null, 'minapappu, minappappu, ulundu, ulutham paruppu, urad'],
  ['chickpeas', 'Chickpeas (boiled/canned)', 'Dals & Beans', 3, 'chana, chole, kabuli chana, boiled chana, chickpea, garbanzo'],
  ['sprouts', 'Moong sprouts', 'Dals & Beans', 3, 'sprouted moong, moong sprouts, mulake, sprout'],
  ['peanuts', 'Peanuts', 'Dals & Beans', null, 'moongphali, mungfali, groundnut, groundnuts, palli, pallilu, verkadalai, shengdana, peanut', { allergens: ['nuts'] }],
  ['cashew', 'Cashews', 'Dals & Beans', null, 'kaju, jeedipappu, mundiri, cashew nuts, cashew', { allergens: ['nuts'] }],
  ['rajma', 'Rajma', 'Dals & Beans', null, 'kidney beans, red beans, rajmah'],
  ['kala_chana', 'Kala chana', 'Dals & Beans', null, 'black chana, black chickpeas, nalla senagalu, kondakadalai'],
  ['lobia', 'Lobia', 'Dals & Beans', null, 'black eyed peas, chawli, alasandalu, karamani'],
  ['soya_chunks', 'Soya chunks', 'Dals & Beans', null, 'soya, soyabean chunks, nutrela, meal maker'],
  // Spices
  ['turmeric', 'Turmeric', 'Spices', null, 'haldi, pasupu, manjal'],
  ['red_chilli_powder', 'Red chilli powder', 'Spices', null, 'lal mirch, chilli powder, chili powder, karam, mirchi powder, kashmiri chilli, red chilli'],
  ['coriander_powder', 'Coriander powder', 'Spices', null, 'dhaniya powder, dhania powder, dhaniyalu podi'],
  ['cumin', 'Cumin seeds', 'Spices', null, 'jeera, zeera, jeelakarra, jeerakam, cumin seeds'],
  ['mustard_seeds', 'Mustard seeds', 'Spices', null, 'rai, sarson, avalu, kadugu, mustard'],
  ['garam_masala', 'Garam masala', 'Spices', null, 'garam masala powder'],
  ['hing', 'Hing', 'Spices', null, 'asafoetida, inguva, perungayam'],
  ['kasuri_methi', 'Kasuri methi', 'Spices', null, 'dried fenugreek leaves, dried methi'],
  ['chaat_masala', 'Chaat masala', 'Spices', null, 'chat masala'],
  ['sambar_powder', 'Sambar powder', 'Spices', null, 'sambar masala, sambhar powder, sambar podi'],
  ['rasam_powder', 'Rasam powder', 'Spices', null, 'rasam masala, charu podi, rasam podi'],
  ['black_pepper', 'Black pepper', 'Spices', null, 'kali mirch, miriyalu, milagu, pepper, pepper powder'],
  ['whole_spices', 'Whole spices', 'Spices', null, 'khada masala, bay leaf, tej patta, cloves, laung, cinnamon, dalchini'],
  ['cardamom', 'Cardamom', 'Spices', null, 'elaichi, elachi, yelakulu, elakkai'],
  ['dry_red_chilli', 'Dry red chilli', 'Spices', null, 'sukhi lal mirch, sabut lal mirch, endu mirapakaya, vara milagai, dried red chilli, red chillies'],
  ['tamarind', 'Tamarind', 'Spices', null, 'imli, chintapandu, puli'],
  ['sesame', 'Sesame seeds', 'Spices', null, 'til, nuvvulu, ellu'],
  // Basics & sauces
  ['salt', 'Salt', 'Basics & Sauces', null, 'namak, uppu'],
  ['oil', 'Cooking oil', 'Basics & Sauces', null, 'tel, nune, enna, sunflower oil, mustard oil, groundnut oil, cooking oil'],
  ['water', 'Water', 'Basics & Sauces', null, 'pani, paani, neellu'],
  ['sugar', 'Sugar', 'Basics & Sauces', null, 'cheeni, chini, shakkar, panchadara'],
  ['jaggery', 'Jaggery', 'Basics & Sauces', null, 'gud, gur, bellam, vellam'],
  ['soy_sauce', 'Soy sauce', 'Basics & Sauces', null, 'soya sauce, soy'],
  ['tomato_ketchup', 'Tomato ketchup', 'Basics & Sauces', null, 'ketchup, tomato sauce'],
  ['vinegar', 'Vinegar', 'Basics & Sauces', null, 'sirka'],
  ['coconut', 'Coconut (grated)', 'Basics & Sauces', 4, 'nariyal, kobbari, thengai, grated coconut, fresh coconut'],
  ['coconut_milk', 'Coconut milk', 'Basics & Sauces', 3, 'nariyal doodh'],
  // Leftovers
  ['leftover_rice', 'Leftover rice', 'Leftovers', 1, 'cooked rice, leftover chawal, left over chawal, leftover annam, bacha hua chawal, baasi chawal, basi chawal, annam, left over rice, yesterday rice, yesterdays rice'],
  ['leftover_roti', 'Leftover roti', 'Leftovers', 1, 'leftover rotis, chapati, chapatis, chapathi, roti, rotis, phulka, leftover chapati', { allergens: ['gluten'] }],
  ['leftover_dal', 'Leftover dal', 'Leftovers', 2, 'cooked dal, leftover pappu, left over dal'],
  ['leftover_sabzi', 'Leftover sabzi', 'Leftovers', 1, 'cooked sabzi, leftover curry, leftover vegetables, leftover sabji, left over sabzi'],
];

export const INGREDIENTS = RAW.map(([id, name, category, shelfDays, aliases, extra = {}]) => ({
  id, name, category, shelfDays,
  aliases: aliases.split(',').map(s => s.trim()).filter(Boolean),
  allergens: extra.allergens || [],
  diet: extra.diet || 'veg',
}));


export const BY_ID = Object.fromEntries(INGREDIENTS.map(i => [i.id, i]));

// Jain cooking avoids onion, garlic and root vegetables.
export const JAIN_BLOCKED = ['onion', 'garlic', 'potato', 'carrot', 'beetroot', 'sweet_potato', 'ginger', 'mushroom', 'spring_onion'];
export const ONION_GARLIC = ['onion', 'garlic', 'spring_onion'];

// One-tap "kits" so a new user can fill the pantry in seconds.
export const KITS = [
  { id: 'masala', name: 'Masala box', items: ['turmeric', 'red_chilli_powder', 'coriander_powder', 'cumin', 'mustard_seeds', 'garam_masala', 'hing', 'sugar'] },
  { id: 'basics', name: 'Everyday basics', items: ['rice', 'atta', 'toor_dal', 'onion', 'tomato', 'potato', 'ginger', 'garlic', 'green_chilli'] },
  { id: 'south', name: 'South Indian tadka', items: ['mustard_seeds', 'urad_dal', 'chana_dal', 'dry_red_chilli', 'hing', 'curry_leaves', 'tamarind', 'sambar_powder'] },
];
