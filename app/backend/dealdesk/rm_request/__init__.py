"""PLAN_R16 session b: the RM business request (the "Action requested" voice of the bank-form proposal).

    inputs.py     the customer file: documents from intake (session i), the demo packs (session d) and the bank's own data
                  (Borrower 360 / Data Domains for an existing customer), normalised to one dict where every figure names its source
    ask.py        the RM's ask typed in the chat box and the RM notes -> requested facilities, terms and attributed notes (rules, no model)
    writers.py    deterministic section writers in the bank-form voice (PROPOSAL_ANATOMY.md §2-§8, §14, plus the RM's justification)
    paper.py      assembly: write(customer_file, ask, notes) -> the business request paper (sections of blocks, figures with sources)
    render.py     Word (house style, the bank-form layout of bankform/render_bank.py)
    relation.py   Data Domains relation dd_business_request (every request written is stored, shareable and reopened)
    store.py      save / read requests
    api.py        /api/v1/dealdesk/business-request*
"""
