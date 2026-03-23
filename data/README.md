# Description

OpenScripture is a open-source dataset for editions of the Book of Mormon and Doctrine and Covenants. OpenScripture.org provides a way to study changes in the Book of Mormon over time by providing easy-to-understand timelines for each word and phrase.

# Goals

The OpenScripture project aims to create digital editions of print editions of the Book of Mormon that are currently not freely accessible on the web. The initial scope of this project is to digitize the 1837, 1840, 1841, 1879, and 1920 editions of the Book of Mormon.

Beyond just creating digital edtions of print editions, they are also being aligned by word and punctuation marks so that variants can be analyzed.

# Timeline

10-Aug-2022: Each edition has been successfully digitized, and we are 60% done with an initial review of each chapter. 1981 and 2013 have also been added to the dataset programatically.

31-Aug-2022: We plan to be 100% with the review.

1-Sep-2022: We will start compiling a similar project for the Book of Commandments/Doctrine and Covenants.

1-Sep-2022 through 31-Dec-2022: Even after the review of the Book of Mormon, we recognize that some chapters contain errors. A second review process will be performed Autumn 2022 to minimize these errors.

# Repository Files

The /book-of-mormon/ folder contains TSV files of each book in the Book of Mormon. Each line contains information about a word, punctuation mark, or space within a scriptural verse. A space is represented with a ⌴ symbol. 

## Columns

1. The first column provides the *modern* scriptural citation of the verse. Any paragraphing used in 1830, 1837, 1840, and 1841 editions are omitted.

2. The second provides a word ID for each row. An integer represented a "head" word, whereas any decimal number is considered a "subword" to the head word.

3. The third column and consecutive columns contain the data on individual editions, starting with the 1830 edition on.

## Symbols

The null symbol (∅) is used to represent that the text doesn't exist in a specific edition.

The space symbol (⌴) is used to represent that there is a space there. This is to help in some CSV/TSV readers that ignore an actual space character.

