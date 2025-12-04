class LeadAggregate:
    def __init__(self, product_name, type, count):
        self.product_name = product_name
        self.type = type
        self.count = count

    def to_dict(self):
        return {
            'product_name': self.product_name,
            'type': self.type,
            'count': self.count,
        }
