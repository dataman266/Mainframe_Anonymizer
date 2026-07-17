       01  CUSTOMER-RECORD.
           05  CUST-ID              PIC 9(08).
           05  CUST-NAME            PIC X(30).
           05  CUST-AGE             PIC 9(03).
           05  CUST-DOB             PIC 9(08).
           05  CUST-STREET-ADDR     PIC X(30).
           05  CUST-CITY            PIC X(20).
           05  CUST-ZIPCODE         PIC X(06).
           05  CUST-SIN             PIC 9(09).
           05  CUST-PHONE           PIC X(12) OCCURS 2 TIMES.
           05  CUST-EMAIL           PIC X(30).
           05  CUST-CARD-NUM        PIC 9(16).
           05  CUST-BALANCE         PIC S9(09)V99 COMP-3.
           05  CUST-BRANCH-CODE     PIC 9(04) COMP.
           05  FILLER               PIC X(10).
