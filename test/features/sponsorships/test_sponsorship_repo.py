import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from db.sql_util import SQLUtil

from features.sponsorships.sponsorship import Sponsorship
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from features.users.user import User


class SponsorshipRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: SponsorshipRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.sponsorship_repo()

    def tearDown(self):
        self.sql.end_session()

    def test_save_creates_pending_sponsorship(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        sponsorship = Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
        )

        result = self.repo.save(sponsorship)

        self.assertEqual(result.sponsor_id, sponsorship.sponsor_id)
        self.assertEqual(result.receiver_id, sponsorship.receiver_id)
        self.assertIsNotNone(result.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_save_creates_accepted_sponsorship(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        accepted_at = datetime.now()
        sponsorship = Sponsorship(
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
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        created = self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
        ))

        result = self.repo.get(sponsor.id, receiver.id)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, created.sponsor_id)
        self.assertEqual(result.receiver_id, created.receiver_id)
        self.assertEqual(result.sponsored_at, created.sponsored_at)
        self.assertEqual(result.accepted_at, created.accepted_at)

    def test_get_returns_none_when_missing(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())

        result = self.repo.get(sponsor.id, receiver.id)

        self.assertIsNone(result)

    def test_get_all_by_sponsor(self):
        sponsor = self.sql.user_repo().save(User())
        receiver1 = self.sql.user_repo().save(User())
        receiver2 = self.sql.user_repo().save(User())
        self.repo.save(Sponsorship(sponsor_id = sponsor.id, receiver_id = receiver1.id))
        self.repo.save(Sponsorship(sponsor_id = sponsor.id, receiver_id = receiver2.id))

        results = self.repo.get_all_by_sponsor(sponsor.id)

        self.assertEqual(len(results), 2)
        self.assertEqual({result.receiver_id for result in results}, {receiver1.id, receiver2.id})
        for result in results:
            self.assertEqual(result.sponsor_id, sponsor.id)

    def test_get_all_by_receiver(self):
        receiver = self.sql.user_repo().save(User())
        sponsor1 = self.sql.user_repo().save(User())
        sponsor2 = self.sql.user_repo().save(User())
        self.repo.save(Sponsorship(sponsor_id = sponsor1.id, receiver_id = receiver.id))
        self.repo.save(Sponsorship(sponsor_id = sponsor2.id, receiver_id = receiver.id))

        results = self.repo.get_all_by_receiver(receiver.id)

        self.assertEqual(len(results), 2)
        self.assertEqual({result.sponsor_id for result in results}, {sponsor1.id, sponsor2.id})
        for result in results:
            self.assertEqual(result.receiver_id, receiver.id)

    def test_get_all_sponsorships(self):
        sponsor1 = self.sql.user_repo().save(User())
        receiver1 = self.sql.user_repo().save(User())
        sponsor2 = self.sql.user_repo().save(User())
        receiver2 = self.sql.user_repo().save(User())
        first = self.repo.save(Sponsorship(sponsor_id = sponsor1.id, receiver_id = receiver1.id))
        second = self.repo.save(Sponsorship(sponsor_id = sponsor2.id, receiver_id = receiver2.id))

        results = self.repo.get_all()

        self.assertEqual({result.sponsor_id for result in results}, {first.sponsor_id, second.sponsor_id})
        self.assertEqual({result.receiver_id for result in results}, {first.receiver_id, second.receiver_id})

    def test_save_updates_accepted_at_and_preserves_sponsored_at_when_replacing_existing(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        created = self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
        ))
        accepted_at = datetime.now()

        result = self.repo.save(replace(created, accepted_at = accepted_at))

        self.assertEqual(result.sponsor_id, created.sponsor_id)
        self.assertEqual(result.receiver_id, created.receiver_id)
        self.assertEqual(result.sponsored_at, created.sponsored_at)
        self.assertEqual(result.accepted_at, accepted_at)

    def test_save_can_clear_accepted_at(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        created = self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
            accepted_at = datetime.now(),
        ))

        result = self.repo.save(replace(created, accepted_at = None))

        self.assertEqual(result.sponsored_at, created.sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_save_can_update_explicit_sponsored_at(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        created = self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
        ))
        sponsored_at = datetime.now() - timedelta(days = 5)

        result = self.repo.save(replace(created, sponsored_at = sponsored_at))

        self.assertEqual(result.sponsored_at, sponsored_at)
        self.assertIsNone(result.accepted_at)

    def test_delete_sponsorship(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())
        created = self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver.id,
        ))

        result = self.repo.delete(sponsor.id, receiver.id)

        self.assertIsNotNone(result)
        self.assertEqual(result.sponsor_id, created.sponsor_id)
        self.assertEqual(result.receiver_id, created.receiver_id)
        self.assertIsNone(self.repo.get(sponsor.id, receiver.id))

    def test_delete_returns_none_when_missing(self):
        sponsor = self.sql.user_repo().save(User())
        receiver = self.sql.user_repo().save(User())

        result = self.repo.delete(sponsor.id, receiver.id)

        self.assertIsNone(result)

    def test_delete_all_by_receiver(self):
        receiver = self.sql.user_repo().save(User())
        sponsor1 = self.sql.user_repo().save(User())
        sponsor2 = self.sql.user_repo().save(User())
        self.repo.save(Sponsorship(sponsor_id = sponsor1.id, receiver_id = receiver.id))
        self.repo.save(Sponsorship(sponsor_id = sponsor2.id, receiver_id = receiver.id))

        deleted_count = self.repo.delete_all_by_receiver(receiver.id)

        self.assertEqual(deleted_count, 2)
        self.assertEqual(len(self.repo.get_all_by_receiver(receiver.id)), 0)

    def test_delete_unaccepted_older_than(self):
        sponsor = self.sql.user_repo().save(User())
        receiver1 = self.sql.user_repo().save(User())
        receiver2 = self.sql.user_repo().save(User())
        receiver3 = self.sql.user_repo().save(User())
        old_sponsored_at = datetime.now() - timedelta(days = 31)
        fresh_sponsored_at = datetime.now()

        self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver1.id,
            sponsored_at = old_sponsored_at,
        ))
        self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver2.id,
            sponsored_at = fresh_sponsored_at,
        ))
        self.repo.save(Sponsorship(
            sponsor_id = sponsor.id,
            receiver_id = receiver3.id,
            sponsored_at = old_sponsored_at,
            accepted_at = datetime.now(),
        ))

        deleted_count = self.repo.delete_unaccepted_older_than(datetime.now() - timedelta(days = 30))

        self.assertEqual(deleted_count, 1)
        self.assertIsNone(self.repo.get(sponsor.id, receiver1.id))
        self.assertIsNotNone(self.repo.get(sponsor.id, receiver2.id))
        self.assertIsNotNone(self.repo.get(sponsor.id, receiver3.id))
