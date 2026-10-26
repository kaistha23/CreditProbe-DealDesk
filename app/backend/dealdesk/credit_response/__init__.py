"""R16 session c: the credit division's response to an uploaded business request.

    case = service.start(files=[("request.pdf", b"..."), ("audited_fs_2025.pdf", b"...")], by="anne")
    case = service.run(case["case_id"])            # parse -> deal -> check -> review -> analysis -> structure -> stress
                                                   #   -> stress-proof -> recommendation -> RM brief -> credit response
    service.response_docx(case_id) / response_pdf(case_id) / brief_docx(case_id)

Deterministic (no model key): every sentence is written by a rule-based writer and every figure names its source
(the uploaded document, page and reading method, or the Data Domains relation and row).
"""
