import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import stubs
from db.sql_util import SQLUtil

from features.sponsorships.sponsorship_repo import SponsorshipRepository

USER_1_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000001")
USER_2_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000002")
USER_3_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000003")
USER_4_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000004")


class SponsorshipRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: SponsorshipRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.sponsorship_repo()

    def tearDown(self):
        self.sql.end_session()

    def test_save_creates_pending_sponsorship(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
            accepted_at = None,
        )

        result = self.repo.save(sponsorship)

        self.assertEqual(result.sponsor_id, sponsorship.sponsor_id)
        self.assertEqual(result.receiver_id, sponsorship.receiver_id)
        self.assertIsNotNone(result.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_save_creates_accepted_sponsorship(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        accepted_at = datetime.now()
        sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
            accepted_at = accepted_at,
        )

        result = self.repo.save(sponsorship)

        self.assertEqual(result.sponsor_id, sponsorship.sponsor_id)
        self.assertEqual(result.receiver_id, sponsorship.receiver_id)
        self.assertIsNotNone(result.sponsored_at)
        self.assertEqual(result.accepted_at, accepted_at)

    def test_get_returns_saved_sponsorship(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        created = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )

        result = self.repo.get(sponsor.id, receiver.id)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, created.sponsor_id)
        self.assertEqual(result.receiver_id, created.receiver_id)
        self.assertEqual(result.sponsored_at, created.sponsored_at)
        self.assertEqual(result.accepted_at, created.accepted_at)

    def test_get_returns_none_when_missing(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )

        result = self.repo.get(sponsor.id, receiver.id)

        self.assertIsNone(result)

    def test_get_all_by_sponsor(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver1 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        receiver2 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_3_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_3_ID)),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver1.id,
                accepted_at = None,
            ),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver2.id,
                accepted_at = None,
            ),
        )

        results = self.repo.get_all_by_sponsor(sponsor.id)

        self.assertEqual(len(results), 2)
        self.assertEqual({result.receiver_id for result in results}, {receiver1.id, receiver2.id})
        for result in results:
            self.assertEqual(result.sponsor_id, sponsor.id)

    def test_get_all_by_receiver(self):
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_3_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_3_ID)),
        )
        sponsor1 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        sponsor2 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor1.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor2.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )

        results = self.repo.get_all_by_receiver(receiver.id)

        self.assertEqual(len(results), 2)
        self.assertEqual({result.sponsor_id for result in results}, {sponsor1.id, sponsor2.id})
        for result in results:
            self.assertEqual(result.receiver_id, receiver.id)

    def test_get_all_sponsorships(self):
        sponsor1 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver1 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        sponsor2 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_3_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_3_ID)),
        )
        receiver2 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_4_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_4_ID)),
        )
        first = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor1.id,
                receiver_id = receiver1.id,
                accepted_at = None,
            ),
        )
        second = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor2.id,
                receiver_id = receiver2.id,
                accepted_at = None,
            ),
        )

        results = self.repo.get_all()

        self.assertEqual({result.sponsor_id for result in results}, {first.sponsor_id, second.sponsor_id})
        self.assertEqual({result.receiver_id for result in results}, {first.receiver_id, second.receiver_id})

    def test_save_updates_accepted_at_and_preserves_sponsored_at_when_replacing_existing(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        created = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )
        accepted_at = datetime.now()

        result = self.repo.save(replace(created, accepted_at = accepted_at))

        self.assertEqual(result.sponsor_id, created.sponsor_id)
        self.assertEqual(result.receiver_id, created.receiver_id)
        self.assertEqual(result.sponsored_at, created.sponsored_at)
        self.assertEqual(result.accepted_at, accepted_at)

    def test_save_can_clear_accepted_at(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        created = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver.id,
                accepted_at = datetime.now(),
            ),
        )

        result = self.repo.save(replace(created, accepted_at = None))

        self.assertEqual(result.sponsored_at, created.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_save_can_update_explicit_sponsored_at(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        created = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )
        sponsored_at = datetime.now() - timedelta(days = 5)

        result = self.repo.save(replace(created, sponsored_at = sponsored_at))

        self.assertEqual(result.sponsored_at, sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_delete_sponsorship(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        created = self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )

        result = self.repo.delete(sponsor.id, receiver.id)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, created.sponsor_id)
        self.assertEqual(result.receiver_id, created.receiver_id)
        self.assertIsNone(self.repo.get(sponsor.id, receiver.id))

    def test_delete_returns_none_when_missing(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )

        result = self.repo.delete(sponsor.id, receiver.id)

        self.assertIsNone(result)

    def test_delete_all_by_receiver(self):
        receiver = self.sql.user_repo().save(
            stubs.domain.user(id = USER_3_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_3_ID)),
        )
        sponsor1 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        sponsor2 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor1.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor2.id,
                receiver_id = receiver.id,
                accepted_at = None,
            ),
        )

        deleted_count = self.repo.delete_all_by_receiver(receiver.id)

        self.assertEqual(deleted_count, 2)
        self.assertEqual(len(self.repo.get_all_by_receiver(receiver.id)), 0)

    def test_delete_unaccepted_older_than(self):
        sponsor = self.sql.user_repo().save(
            stubs.domain.user(id = USER_1_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_1_ID)),
        )
        receiver1 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_2_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_2_ID)),
        )
        receiver2 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_3_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_3_ID)),
        )
        receiver3 = self.sql.user_repo().save(
            stubs.domain.user(id = USER_4_ID, telegram_user_id = None, whatsapp_user_id = None, connect_key = str(USER_4_ID)),
        )
        old_sponsored_at = datetime.now() - timedelta(days = 31)
        fresh_sponsored_at = datetime.now()

        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver1.id,
                sponsored_at = old_sponsored_at,
                accepted_at = None,
            ),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver2.id,
                sponsored_at = fresh_sponsored_at,
                accepted_at = None,
            ),
        )
        self.repo.save(
            stubs.domain.sponsorship(
                sponsor_id = sponsor.id,
                receiver_id = receiver3.id,
                sponsored_at = old_sponsored_at,
                accepted_at = datetime.now(),
            ),
        )

        deleted_count = self.repo.delete_unaccepted_older_than(datetime.now() - timedelta(days = 30))

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get(sponsor.id, receiver1.id))
        self.assertIsNotNone(self.repo.get(sponsor.id, receiver2.id))
        self.assertIsNotNone(self.repo.get(sponsor.id, receiver3.id))
