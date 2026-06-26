"""The curated trivia question bank — a large, diverse, multi-topic pool.

A single flat tuple of :class:`~kenning.twitch.economy.games.TriviaQuestion`
spanning many categories (science, space, history, geography, world capitals,
pop culture, movies & TV, music, sports, video games, literature, food & drink,
nature & animals, technology & computing, mythology, art, math/logic, and
general knowledge) — plus the original Valorant/gaming questions so the channel
keeps its on-theme rounds.

Each entry is ``TriviaQuestion(question, answer, accept=(...))`` where:
  * ``question`` is a clear, unambiguous one-line prompt,
  * ``answer`` is the concise canonical answer (the one Ultron announces), and
  * ``accept`` is a tuple of additional acceptable spellings/aliases.

Matching is case-insensitive + whitespace-stripped against the canonical answer
OR any alias (see :meth:`Trivia.check_answer`). Keep answers SHORT and aliases
natural (digits vs words, common abbreviations, alternate names) so a correct
chatter is not robbed by a spelling nitpick, while wrong answers still fail.

ANTICHEAT (BR-P1): pure data + stdlib typing only. No imports beyond the
sibling ``games`` dataclass.
"""
from __future__ import annotations

from kenning.twitch.economy.games import TriviaQuestion as _Q

__all__ = ["TRIVIA_QUESTIONS"]


# ---------------------------------------------------------------------------
# The bank. Grouped by category only for readability — at runtime it is one
# flat pool. Answers verified for correctness; aliases cover the natural ways a
# chatter would type the same answer (number words, abbreviations, alt names).
# ---------------------------------------------------------------------------
TRIVIA_QUESTIONS: tuple[_Q, ...] = (
    # --- Valorant / gaming (kept from the original pool) -------------------
    _Q("How many rounds does it take to win a standard Valorant match?", "13"),
    _Q("What is the name of Jett's ultimate ability?", "blade storm",
       accept=("bladestorm",)),
    _Q("Which Valorant agent can resurrect a fallen ally?", "sage"),
    _Q("What is the buy phase timer in Valorant, in seconds?", "30",
       accept=("thirty",)),
    _Q("What is the name of Omen's ultimate ability?", "from the shadows"),
    _Q("Which Valorant map is set in Morocco?", "pearl"),
    _Q("How many players are on each team in a Valorant match?", "5",
       accept=("five",)),
    _Q("What is the name of Reyna's heal ability?", "devour"),
    _Q("Which Valorant agent uses an owl drone to scout?", "sova"),
    _Q("How many seconds does the Spike take to detonate after being planted?",
       "45", accept=("forty-five", "forty five")),
    _Q("Which Valorant map was the first added after launch?", "icebox"),
    _Q("In Minecraft, which hostile mob explodes when it gets close to you?",
       "creeper"),
    _Q("What is the best-selling video game of all time?", "minecraft"),
    _Q("In Pac-Man, what does Pac-Man eat to turn the ghosts blue?",
       "power pellet", accept=("power pellets", "power-up", "energizer")),
    _Q("Which company created the game Fortnite?", "epic games",
       accept=("epic",)),
    _Q("In the Pokemon games, what type is super effective against Water?",
       "grass", accept=("electric",)),
    _Q("What is the name of the princess Mario usually rescues?", "peach",
       accept=("princess peach",)),
    _Q("Which video game features a silent protagonist named Gordon Freeman?",
       "half-life", accept=("half life", "halflife")),

    # --- Science ----------------------------------------------------------
    _Q("What is the chemical symbol for gold?", "au"),
    _Q("What gas do plants absorb from the atmosphere for photosynthesis?",
       "carbon dioxide", accept=("co2", "co-2")),
    _Q("How many bones are in the adult human body?", "206",
       accept=("two hundred six", "two hundred and six")),
    _Q("What is the most abundant gas in Earth's atmosphere?", "nitrogen"),
    _Q("What is the powerhouse of the cell?", "mitochondria",
       accept=("the mitochondria", "mitochondrion")),
    _Q("What is the chemical symbol for iron?", "fe"),
    _Q("What force keeps us anchored to the ground?", "gravity"),
    _Q("What is the hardest known natural material?", "diamond"),
    _Q("At what temperature in Celsius does water boil at sea level?", "100",
       accept=("one hundred",)),
    _Q("What is the pH of pure water?", "7", accept=("seven",)),
    _Q("Which metal in human blood binds and carries oxygen?", "iron"),
    _Q("What is the speed of light commonly rounded to, in km per second?",
       "300000", accept=("300,000", "three hundred thousand")),
    _Q("What scientist developed the theory of general relativity?",
       "einstein", accept=("albert einstein",)),
    _Q("What is H2O more commonly known as?", "water"),
    _Q("What part of the human body produces insulin?", "pancreas"),
    _Q("How many chambers does a human heart have?", "4", accept=("four",)),
    _Q("What is the lightest element on the periodic table?", "hydrogen"),
    _Q("What blood type is the universal donor?", "o negative",
       accept=("o-", "o neg", "type o negative")),

    # --- Space / astronomy ------------------------------------------------
    _Q("Which planet is known as the Red Planet?", "mars"),
    _Q("What is the closest planet to the Sun?", "mercury"),
    _Q("What is the largest planet in our solar system?", "jupiter"),
    _Q("What is the name of Earth's only natural satellite?", "the moon",
       accept=("moon", "luna")),
    _Q("Which galaxy is Earth located in?", "the milky way",
       accept=("milky way",)),
    _Q("Who was the first person to walk on the Moon?", "neil armstrong",
       accept=("armstrong",)),
    _Q("What is the name of the force that pulls everything toward a black "
       "hole's center?", "gravity"),
    _Q("How many planets are in our solar system?", "8", accept=("eight",)),
    _Q("What star is at the center of our solar system?", "the sun",
       accept=("sun", "sol")),
    _Q("Which planet has the most prominent ring system?", "saturn"),
    _Q("What is the name of the first artificial satellite launched into "
       "space?", "sputnik", accept=("sputnik 1", "sputnik-1")),
    _Q("What was the name of the telescope launched in 1990 that orbits "
       "Earth?", "hubble", accept=("hubble space telescope",)),

    # --- History ----------------------------------------------------------
    _Q("In what year did World War II end?", "1945"),
    _Q("Who was the first President of the United States?",
       "george washington", accept=("washington",)),
    _Q("Which ancient civilization built the pyramids of Giza?", "egyptians",
       accept=("ancient egyptians", "egypt", "ancient egypt")),
    _Q("What wall fell in 1989, reuniting a divided city?", "berlin wall",
       accept=("the berlin wall",)),
    _Q("Who painted the ceiling of the Sistine Chapel?", "michelangelo"),
    _Q("In what year did the Titanic sink?", "1912"),
    _Q("Which queen ruled the United Kingdom for over 70 years until 2022?",
       "elizabeth ii", accept=("queen elizabeth ii", "elizabeth the second",
                                "queen elizabeth")),
    _Q("What document, signed in 1776, declared American independence?",
       "declaration of independence",
       accept=("the declaration of independence",)),
    _Q("Who was the British Prime Minister during most of World War II?",
       "winston churchill", accept=("churchill",)),
    _Q("Which empire was ruled by Julius Caesar?", "roman empire",
       accept=("rome", "the roman empire", "roman")),
    _Q("What year did the first man land on the Moon?", "1969"),
    _Q("Which explorer is credited with reaching the Americas in 1492?",
       "christopher columbus", accept=("columbus",)),

    # --- Geography --------------------------------------------------------
    _Q("What is the largest country in the world by area?", "russia"),
    _Q("What is the longest river in the world?", "the nile",
       accept=("nile", "nile river")),
    _Q("Which is the largest ocean on Earth?", "pacific",
       accept=("pacific ocean", "the pacific ocean")),
    _Q("What is the smallest country in the world?", "vatican city",
       accept=("vatican", "the vatican")),
    _Q("On which continent is the Sahara Desert located?", "africa"),
    _Q("What is the tallest mountain on Earth above sea level?",
       "mount everest", accept=("everest",)),
    _Q("Which country has the most people in the world?", "india"),
    _Q("What is the largest desert in the world?", "antarctica",
       accept=("antarctic", "the antarctic")),
    _Q("Which US state is the largest by area?", "alaska"),
    _Q("What body of water separates England from France?",
       "english channel", accept=("the english channel", "the channel")),
    _Q("Which African country was never colonized by a European power?",
       "ethiopia"),
    _Q("What is the longest wall in the world, visible across China?",
       "great wall of china", accept=("the great wall of china",
                                       "great wall", "the great wall")),

    # --- World capitals ---------------------------------------------------
    _Q("What is the capital of France?", "paris"),
    _Q("What is the capital of Japan?", "tokyo"),
    _Q("What is the capital of Australia?", "canberra"),
    _Q("What is the capital of Canada?", "ottawa"),
    _Q("What is the capital of Egypt?", "cairo"),
    _Q("What is the capital of Brazil?", "brasilia", accept=("brasília",)),
    _Q("What is the capital of Italy?", "rome"),
    _Q("What is the capital of Russia?", "moscow"),
    _Q("What is the capital of South Korea?", "seoul"),
    _Q("What is the capital of Spain?", "madrid"),
    _Q("What is the capital of Germany?", "berlin"),
    _Q("What is the capital of Greece?", "athens"),

    # --- Pop culture / movies & TV ----------------------------------------
    _Q("Which superhero is known as the Caped Crusader?", "batman"),
    _Q("In the Harry Potter series, what is the name of Harry's pet owl?",
       "hedwig"),
    _Q("What is the highest-grossing film of all time (unadjusted)?",
       "avatar"),
    _Q("Which animated movie features a snowman named Olaf?", "frozen"),
    _Q("Who directed the movie Jaws and Jurassic Park?",
       "steven spielberg", accept=("spielberg",)),
    _Q("In Star Wars, who is Luke Skywalker's father?", "darth vader",
       accept=("vader", "anakin", "anakin skywalker")),
    _Q("What is the name of the coffee shop in the TV show Friends?",
       "central perk"),
    _Q("Which movie features the quote, 'I'll be back'?", "the terminator",
       accept=("terminator",)),
    _Q("In The Lion King, what is the name of Simba's father?", "mufasa"),
    _Q("What fictional metal is Wolverine's skeleton coated with?",
       "adamantium"),
    _Q("Which streaming show features a series of deadly children's games for "
       "money?", "squid game", accept=("the squid game",)),
    _Q("Who plays Iron Man in the Marvel Cinematic Universe?",
       "robert downey jr", accept=("robert downey jr.", "rdj",
                                    "robert downey junior")),

    # --- Music ------------------------------------------------------------
    _Q("Which British band released the album 'Abbey Road'?", "the beatles",
       accept=("beatles",)),
    _Q("Who is known as the 'King of Pop'?", "michael jackson"),
    _Q("How many strings does a standard guitar have?", "6", accept=("six",)),
    _Q("Which instrument has 88 keys?", "piano", accept=("the piano",)),
    _Q("Who sang the 1992 hit 'I Will Always Love You'?",
       "whitney houston"),
    _Q("What genre of music is Bob Marley most associated with?", "reggae"),
    _Q("Which artist released the album '1989' and the song 'Shake It Off'?",
       "taylor swift"),
    _Q("How many lines are in a traditional limerick?", "5", accept=("five",)),
    _Q("What is the best-selling music album of all time?", "thriller"),
    _Q("Which classical composer was deaf for much of his later life?",
       "beethoven", accept=("ludwig van beethoven",)),

    # --- Sports -----------------------------------------------------------
    _Q("How many players are on a soccer team on the field at one time?",
       "11", accept=("eleven",)),
    _Q("In which sport would you perform a slam dunk?", "basketball"),
    _Q("How many points is a touchdown worth in American football?", "6",
       accept=("six",)),
    _Q("Which country has won the most FIFA World Cups?", "brazil"),
    _Q("In tennis, what is the term for zero points?", "love"),
    _Q("How often are the Summer Olympic Games held, in years?", "4",
       accept=("four", "every four years")),
    _Q("What sport is played at Wimbledon?", "tennis"),
    _Q("How many holes are played in a standard round of golf?", "18",
       accept=("eighteen",)),
    _Q("In which sport is the term 'home run' used?", "baseball"),
    _Q("How many rings are on the Olympic flag?", "5", accept=("five",)),
    _Q("What is the maximum score possible in a single game of ten-pin "
       "bowling?", "300", accept=("three hundred",)),

    # --- Literature -------------------------------------------------------
    _Q("Who wrote the play 'Romeo and Juliet'?", "shakespeare",
       accept=("william shakespeare",)),
    _Q("In which novel would you meet a character named Sherlock Holmes?",
       "a study in scarlet", accept=("the adventures of sherlock holmes",
                                      "sherlock holmes")),
    _Q("Who wrote the dystopian novel '1984'?", "george orwell",
       accept=("orwell",)),
    _Q("What is the first book of the Christian Bible?", "genesis"),
    _Q("Who wrote 'Pride and Prejudice'?", "jane austen", accept=("austen",)),
    _Q("In Greek-inspired fiction, what boy never grows up in J. M. Barrie's "
       "tale?", "peter pan"),
    _Q("Who is the author of the Harry Potter book series?",
       "j.k. rowling", accept=("jk rowling", "j. k. rowling", "rowling",
                                "joanne rowling")),
    _Q("Which Roald Dahl book features a boy who wins a golden ticket?",
       "charlie and the chocolate factory"),
    _Q("Who wrote 'The Adventures of Tom Sawyer'?", "mark twain",
       accept=("twain", "samuel clemens")),

    # --- Food & drink -----------------------------------------------------
    _Q("What fruit is traditionally used to make wine?", "grapes",
       accept=("grape",)),
    _Q("What is the main ingredient in guacamole?", "avocado",
       accept=("avocados",)),
    _Q("Which spice is the most expensive in the world by weight?",
       "saffron"),
    _Q("What type of pasta is shaped like little bow ties?", "farfalle"),
    _Q("From which country did sushi originate?", "japan"),
    _Q("What is the main ingredient in traditional hummus?", "chickpeas",
       accept=("chickpea", "garbanzo beans", "garbanzo")),
    _Q("What beverage is made from roasted, ground coffee beans?", "coffee"),
    _Q("What is the most consumed beverage in the world after water?", "tea"),
    _Q("What nut is used to make marzipan?", "almonds", accept=("almond",)),
    _Q("What is the name of the Italian dish of thin-sliced raw beef?",
       "carpaccio"),

    # --- Nature & animals -------------------------------------------------
    _Q("What is the largest land animal on Earth?", "elephant",
       accept=("african elephant", "elephants")),
    _Q("What is the fastest land animal?", "cheetah"),
    _Q("How many legs does a spider have?", "8", accept=("eight",)),
    _Q("What is the largest mammal in the world?", "blue whale",
       accept=("the blue whale",)),
    _Q("What do bees collect from flowers to make honey?", "nectar"),
    _Q("Which bird is known for its ability to mimic human speech?", "parrot",
       accept=("parrots",)),
    _Q("What is a group of lions called?", "a pride", accept=("pride",)),
    _Q("What is the only mammal capable of true flight?", "bat",
       accept=("bats",)),
    _Q("What is the tallest animal in the world?", "giraffe"),
    _Q("How many hearts does an octopus have?", "3", accept=("three",)),
    _Q("What animal is known as man's best friend?", "dog", accept=("dogs",)),

    # --- Technology & computing -------------------------------------------
    _Q("What does CPU stand for?", "central processing unit"),
    _Q("Who co-founded Microsoft with Paul Allen?", "bill gates",
       accept=("gates", "william gates")),
    _Q("What does 'WWW' stand for?", "world wide web",
       accept=("the world wide web",)),
    _Q("What company makes the iPhone?", "apple"),
    _Q("In computing, how many bits are in a byte?", "8", accept=("eight",)),
    _Q("What does 'HTML' stand for?", "hypertext markup language"),
    _Q("What programming language shares its name with a type of snake?",
       "python"),
    _Q("Who is the founder and CEO of Tesla and SpaceX?", "elon musk",
       accept=("musk",)),
    _Q("What does 'RAM' stand for in computers?", "random access memory"),
    _Q("What search engine's name has become a verb for looking things up "
       "online?", "google"),
    _Q("What is the binary number system's base?", "2", accept=("two",)),

    # --- Mythology --------------------------------------------------------
    _Q("In Greek mythology, who is the king of the gods?", "zeus"),
    _Q("In Norse mythology, who wields the hammer Mjolnir?", "thor"),
    _Q("In Greek mythology, who is the god of the sea?", "poseidon"),
    _Q("What is the name of the winged horse in Greek mythology?", "pegasus"),
    _Q("In Greek mythology, who flew too close to the sun on wax wings?",
       "icarus"),
    _Q("In Egyptian mythology, who is the god of the underworld and the dead?",
       "anubis", accept=("osiris",)),
    _Q("What three-headed dog guards the underworld in Greek mythology?",
       "cerberus"),
    _Q("In Roman mythology, who is the counterpart of the Greek god Zeus?",
       "jupiter"),
    _Q("In Greek mythology, what creature had snakes for hair and turned "
       "people to stone?", "medusa"),

    # --- Art --------------------------------------------------------------
    _Q("Who painted the Mona Lisa?", "leonardo da vinci",
       accept=("da vinci", "leonardo",)),
    _Q("Which artist cut off part of his own ear?", "van gogh",
       accept=("vincent van gogh",)),
    _Q("What art movement is Pablo Picasso most associated with?", "cubism"),
    _Q("In which country is the Louvre museum located?", "france"),
    _Q("Which Dutch artist painted 'The Starry Night'?", "van gogh",
       accept=("vincent van gogh",)),
    _Q("What painting technique uses small dots of color?", "pointillism"),
    _Q("Who sculpted the statue of David in Florence?", "michelangelo"),

    # --- Math / logic -----------------------------------------------------
    _Q("What is 7 times 8?", "56", accept=("fifty-six", "fifty six")),
    _Q("How many sides does a hexagon have?", "6", accept=("six",)),
    _Q("What is the value of pi rounded to two decimal places?", "3.14"),
    _Q("What is the square root of 144?", "12", accept=("twelve",)),
    _Q("How many degrees are in a right angle?", "90", accept=("ninety",)),
    _Q("What is 15 percent of 200?", "30", accept=("thirty",)),
    _Q("How many sides does a triangle have?", "3", accept=("three",)),
    _Q("What is the next prime number after 7?", "11", accept=("eleven",)),
    _Q("How many degrees are in a full circle?", "360",
       accept=("three hundred sixty", "three hundred and sixty")),
    _Q("What do you call a number that can only be divided by 1 and itself?",
       "prime number", accept=("prime", "a prime number", "a prime")),

    # --- General knowledge ------------------------------------------------
    _Q("How many colors are in a rainbow?", "7", accept=("seven",)),
    _Q("What is the currency used in Japan?", "yen", accept=("japanese yen",)),
    _Q("How many days are there in a leap year?", "366",
       accept=("three hundred sixty-six", "three hundred and sixty six")),
    _Q("What is the tallest building in the world?", "burj khalifa",
       accept=("the burj khalifa",)),
    _Q("How many continents are there on Earth?", "7", accept=("seven",)),
    _Q("What is the freezing point of water in Fahrenheit?", "32",
       accept=("thirty-two", "thirty two")),
    _Q("How many minutes are in a full day?", "1440",
       accept=("1,440", "one thousand four hundred forty")),
    _Q("What color do you get when you mix blue and yellow?", "green"),
    _Q("How many letters are in the English alphabet?", "26",
       accept=("twenty-six", "twenty six")),
    _Q("What is the largest organ in the human body?", "skin",
       accept=("the skin",)),
    _Q("How many sides does a stop sign have?", "8", accept=("eight",)),
    _Q("What is the most spoken language in the world by native speakers?",
       "mandarin", accept=("mandarin chinese", "chinese")),
    _Q("How many zeros are in one million?", "6", accept=("six",)),
    _Q("What is the national animal of China?", "panda",
       accept=("giant panda", "the panda")),
)
