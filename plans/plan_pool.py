import json
import db
from datetime import datetime

class PlanPool:
    def get_active_plans(self):
        return db.get_active_plans()

    def get_plan(self, plan_id):
        plans = db.get_active_plans()
        for p in plans:
            if p['plan_id'] == plan_id:
                return p
        return None

    def save_plans(self, plans_dict):
        for trader_name, plan_data in plans_dict.items():
            week_start = plan_data.get('week_start', datetime.now().strftime('%Y-%m-%d'))
            week_end = plan_data.get('week_end', datetime.now().strftime('%Y-%m-%d'))
            plan_id = f"{trader_name}_{week_start}"
            plan_json = json.dumps(plan_data, ensure_ascii=False)
            db.save_trading_plan(plan_id, trader_name, trader_name, week_start, week_end, plan_json)
            print(f"  📝 方案已保存: {plan_id} ({len(plan_data.get('rules', []))} 条规则)")

    def archive_all_active(self):
        plans = db.get_active_plans()
        for p in plans:
            db.archive_plan(p['plan_id'])
        print(f"  📦 已归档 {len(plans)} 个方案")

    def modify_rule(self, plan_id, rule_id, updates):
        plan = self.get_plan(plan_id)
        if not plan:
            return False
        try:
            data = json.loads(plan['plan_json']) if isinstance(plan['plan_json'], str) else plan['plan_json']
            for rule in data.get('rules', []):
                if rule.get('rule_id') == rule_id:
                    rule.update(updates)
                    break
            new_json = json.dumps(data, ensure_ascii=False)
            db.save_trading_plan(plan_id, plan['trader'], plan['account_id'], plan['week_start'], plan['week_end'], new_json)
            return True
        except Exception as e:
            print(f"  ❌ 修改方案失败: {e}")
            return False

    def disable_rule(self, plan_id, rule_id):
        return db.disable_plan_rule(plan_id, rule_id)

    def add_rule(self, plan_id, new_rule):
        plan = self.get_plan(plan_id)
        if not plan:
            return False
        try:
            data = json.loads(plan['plan_json']) if isinstance(plan['plan_json'], str) else plan['plan_json']
            max_id = max((r.get('rule_id', 0) for r in data.get('rules', [])), default=0)
            new_rule['rule_id'] = max_id + 1
            data.setdefault('rules', []).append(new_rule)
            new_json = json.dumps(data, ensure_ascii=False)
            db.save_trading_plan(plan_id, plan['trader'], plan['account_id'], plan['week_start'], plan['week_end'], new_json)
            return True
        except Exception as e:
            print(f"  ❌ 新增规则失败: {e}")
            return False

    def print_active_summary(self):
        plans = self.get_active_plans()
        print(f"\n{'='*60}")
        print(f"📊 当前活跃方案池 ({len(plans)} 个)")
        print(f"{'='*60}")
        for p in plans:
            try:
                data = json.loads(p['plan_json']) if isinstance(p['plan_json'], str) else p['plan_json']
                rules = data.get('rules', [])
                print(f"  [{p['trader']}] {p['plan_id']} | {p['week_start']}~{p['week_end']} | {len(rules)} 规则 | outlook: {data.get('market_outlook', '-')[:40]}")
            except:
                print(f"  [{p['trader']}] {p['plan_id']}")
        print()
